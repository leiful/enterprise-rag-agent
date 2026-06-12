export function useKnowledgeManagement({
  API_BASE,
  responseError,
  refs,
  loaders,
  fetchImpl = fetch,
  FormDataImpl = FormData,
  setTimeoutImpl = globalThis.setTimeout,
}) {
  const {
    ragStatus,
    knowledgeFileInput,
    selectedKnowledgeFile,
    knowledgeNotes,
    knowledgeDepartment,
    knowledgeLoading,
    knowledgeError,
    knowledgeIndexJob,
    knowledgeSources,
    knowledgeSearchQuery,
    knowledgeSearchResults,
    knowledgeSearchLoading,
    knowledgeSearchError,
  } = refs;
  const {
    loadKnowledgeSources,
    loadKnowledgeDocuments,
    loadRagStatus,
    loadKnowledgeAudits,
  } = loaders;

  function defaultKnowledgeTopK() {
    return Number(ragStatus.value?.retrieval?.default_top_k || 5);
  }

  function defaultKnowledgeMinScore() {
    return Number(ragStatus.value?.retrieval?.default_min_score ?? 0.25);
  }

  function chooseKnowledgeFile() {
    knowledgeFileInput.value?.click();
  }

  function onKnowledgeFileChange(event) {
    selectedKnowledgeFile.value = event.target.files?.[0] || null;
  }

  async function wait(delay) {
    await new Promise((resolve) => setTimeoutImpl(resolve, delay));
  }

  async function pollKnowledgeIndexJob(jobId) {
    if (!jobId) {
      return;
    }

    for (let attempt = 0; attempt < 120; attempt += 1) {
      const response = await fetchImpl(`${API_BASE}/knowledge/index-jobs/${encodeURIComponent(jobId)}`, {
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error(`Index job polling failed with status ${response.status}`);
      }

      const data = await response.json();
      knowledgeIndexJob.value = data;

      if (data.status === "completed") {
        await loadKnowledgeDocuments();
        await loadRagStatus();
        return;
      }

      if (data.status === "failed") {
        throw new Error(data.error || "Indexing failed");
      }

      await wait(1000);
    }

    throw new Error("Indexing is taking too long, please check again later.");
  }

  async function pollKnowledgeIndexJobs(jobs) {
    const jobIds = (jobs || []).map((job) => job.job_id).filter(Boolean);
    if (jobIds.length === 0) {
      await loadKnowledgeSources();
      await loadKnowledgeDocuments();
      await loadRagStatus();
      return;
    }

    for (let attempt = 0; attempt < 120; attempt += 1) {
      const responses = await Promise.all(
        jobIds.map((jobId) =>
          fetchImpl(`${API_BASE}/knowledge/index-jobs/${encodeURIComponent(jobId)}`, {
            credentials: "include",
          }).then((response) => {
            if (!response.ok) {
              throw new Error(`Index job polling failed with status ${response.status}`);
            }
            return response.json();
          }),
        ),
      );

      const completed = responses.filter((job) => job.status === "completed").length;
      const failed = responses.filter((job) => job.status === "failed").length;
      const running = responses.length - completed - failed;
      knowledgeIndexJob.value = {
        status: running > 0 ? "running" : failed > 0 ? "failed" : "completed",
        document_id: `${completed} completed, ${failed} failed, ${running} running`,
      };

      if (completed + failed === responses.length) {
        await loadKnowledgeSources();
        await loadKnowledgeDocuments();
        await loadRagStatus();
        if (failed > 0) {
          throw new Error(`${failed} index job(s) failed`);
        }
        return;
      }

      await wait(1000);
    }

    throw new Error("Indexing is taking too long, please check again later.");
  }

  async function uploadKnowledgeFile() {
    const file = selectedKnowledgeFile.value;

    if (!file || knowledgeLoading.value) {
      return;
    }

    if (file.size > 50 * 1024 * 1024) {
      knowledgeError.value = "File is larger than 50MB.";
      return;
    }

    knowledgeLoading.value = true;
    knowledgeError.value = "";
    knowledgeIndexJob.value = null;

    try {
      const formData = new FormDataImpl();
      formData.append("file", file);
      formData.append("notes", knowledgeNotes.value.trim());
      formData.append(
        "metadata",
        JSON.stringify({
          department: knowledgeDepartment.value.trim(),
        }),
      );

      const response = await fetchImpl(`${API_BASE}/knowledge/upload`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(
          await responseError(response, `Upload failed with status ${response.status}`),
        );
      }

      const data = await response.json();
      knowledgeIndexJob.value = data;
      selectedKnowledgeFile.value = null;
      knowledgeNotes.value = "";
      knowledgeDepartment.value = "";
      if (knowledgeFileInput.value) {
        knowledgeFileInput.value.value = "";
      }
      await pollKnowledgeIndexJob(data.job_id);
    } catch (err) {
      knowledgeError.value = err.message || "Upload failed";
    } finally {
      knowledgeLoading.value = false;
    }
  }

  async function deleteKnowledgeDocument(documentId) {
    if (knowledgeLoading.value) {
      return;
    }

    knowledgeLoading.value = true;
    knowledgeError.value = "";

    try {
      const response = await fetchImpl(
        `${API_BASE}/knowledge/documents/${encodeURIComponent(documentId)}`,
        {
          method: "DELETE",
          credentials: "include",
        },
      );

      if (!response.ok) {
        throw new Error(`Delete failed with status ${response.status}`);
      }

      await loadKnowledgeDocuments();
      await loadRagStatus();
    } catch (err) {
      knowledgeError.value = err.message || "Delete failed";
    } finally {
      knowledgeLoading.value = false;
    }
  }

  async function reindexAllKnowledgeDocuments() {
    if (knowledgeLoading.value) {
      return;
    }

    knowledgeLoading.value = true;
    knowledgeError.value = "";
    knowledgeIndexJob.value = null;

    try {
      const response = await fetchImpl(`${API_BASE}/knowledge/reindex`, {
        method: "POST",
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error(
          await responseError(response, `Batch reindex failed with status ${response.status}`),
        );
      }

      const data = await response.json();
      knowledgeIndexJob.value = {
        status: "queued",
        document_id: `${data.queued_count} documents queued, ${data.skipped_count} skipped`,
      };
      await loadKnowledgeDocuments();
      await loadRagStatus();
    } catch (err) {
      knowledgeError.value = err.message || "Batch reindex failed";
    } finally {
      knowledgeLoading.value = false;
    }
  }

  async function syncKnowledgeSource(sourceId) {
    const response = await fetchImpl(`${API_BASE}/knowledge/sources/${sourceId}/sync`, {
      method: "POST",
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(
        await responseError(response, `Source sync failed with status ${response.status}`),
      );
    }

    return response.json();
  }

  async function syncEnabledKnowledgeSources() {
    if (knowledgeLoading.value) {
      return;
    }

    const enabledSources = knowledgeSources.value.filter((source) => source.enabled);
    if (enabledSources.length === 0) {
      return;
    }

    knowledgeLoading.value = true;
    knowledgeError.value = "";
    knowledgeIndexJob.value = null;

    try {
      let queuedCount = 0;
      let unchangedCount = 0;
      let missingCount = 0;
      const jobs = [];
      for (const source of enabledSources) {
        const data = await syncKnowledgeSource(source.id);
        queuedCount += Number(data.queued_count || 0);
        unchangedCount += Number(data.unchanged_count || 0);
        missingCount += Number(data.missing_count || 0);
        jobs.push(...(data.jobs || []));
      }
      knowledgeIndexJob.value = {
        status: "queued",
        document_id: `${queuedCount} source files queued, ${unchangedCount} unchanged, ${missingCount} missing`,
      };
      await pollKnowledgeIndexJobs(jobs);
    } catch (err) {
      knowledgeError.value = err.message || "Source sync failed";
    } finally {
      knowledgeLoading.value = false;
    }
  }

  async function clearMissingKnowledgeFiles() {
    if (knowledgeLoading.value) {
      return;
    }

    knowledgeLoading.value = true;
    knowledgeError.value = "";

    try {
      const response = await fetchImpl(`${API_BASE}/knowledge/sources/missing-files`, {
        method: "DELETE",
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error(
          await responseError(response, `Clear missing files failed with status ${response.status}`),
        );
      }

      await loadKnowledgeSources();
      await loadRagStatus();
    } catch (err) {
      knowledgeError.value = err.message || "Clear missing files failed";
    } finally {
      knowledgeLoading.value = false;
    }
  }

  async function deduplicateKnowledgeDocuments() {
    if (knowledgeLoading.value) {
      return;
    }

    knowledgeLoading.value = true;
    knowledgeError.value = "";
    knowledgeIndexJob.value = null;

    try {
      const response = await fetchImpl(`${API_BASE}/knowledge/documents/deduplicate`, {
        method: "POST",
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error(
          await responseError(response, `Deduplicate failed with status ${response.status}`),
        );
      }

      const data = await response.json();
      knowledgeIndexJob.value = {
        status: "completed",
        document_id: `${data.removed_count || 0} duplicate document(s) removed`,
      };
      await loadKnowledgeSources();
      await loadKnowledgeDocuments();
      await loadRagStatus();
    } catch (err) {
      knowledgeError.value = err.message || "Deduplicate failed";
    } finally {
      knowledgeLoading.value = false;
    }
  }

  async function searchKnowledge() {
    const query = knowledgeSearchQuery.value.trim();

    if (!query || knowledgeSearchLoading.value) {
      return;
    }

    knowledgeSearchLoading.value = true;
    knowledgeSearchError.value = "";

    try {
      const response = await fetchImpl(`${API_BASE}/knowledge/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({
          query,
          top_k: defaultKnowledgeTopK(),
          min_score: defaultKnowledgeMinScore(),
        }),
      });

      if (!response.ok) {
        throw new Error(
          await responseError(response, `Search failed with status ${response.status}`),
        );
      }

      const data = await response.json();
      knowledgeSearchResults.value = data.results || [];
      await loadKnowledgeAudits();
      await loadRagStatus();
    } catch (err) {
      knowledgeSearchError.value = err.message || "Search failed";
      knowledgeSearchResults.value = [];
    } finally {
      knowledgeSearchLoading.value = false;
    }
  }

  return {
    defaultKnowledgeTopK,
    defaultKnowledgeMinScore,
    chooseKnowledgeFile,
    onKnowledgeFileChange,
    uploadKnowledgeFile,
    pollKnowledgeIndexJob,
    pollKnowledgeIndexJobs,
    deleteKnowledgeDocument,
    reindexAllKnowledgeDocuments,
    syncKnowledgeSource,
    syncEnabledKnowledgeSources,
    clearMissingKnowledgeFiles,
    deduplicateKnowledgeDocuments,
    searchKnowledge,
  };
}
