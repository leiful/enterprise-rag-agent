# RAG Design

The project uses RAG mode B. Before each user question is sent to the model, the backend first performs a knowledge-base preflight search.

The RAG flow is:

1. The user sends a question.
2. The backend searches the indexed knowledge base.
3. The system retrieves the top candidate chunks.
4. The system filters results with a minimum score.
5. If relevant evidence exists, the backend injects the chunks into the model context.
6. The model answers from the relevant snippets and cites sources with labels such as [K1] and [K2].
7. If the snippets are missing or unrelated, the model must say that the knowledge base does not contain enough evidence.
8. After that, the model may use general knowledge, but it must not cite unrelated knowledge-base snippets.

The default retrieval parameters are top_k=3 and min_score=0.3.

The current implementation relies on direct retrieval from indexed chunks. It does not currently implement query rewrite, multi-query retrieval, or rerank model scoring.

LangChain is not introduced yet because the project is still in a learning phase. The hand-written RAG pipeline makes chunking, embedding, retrieval, prompt injection, and source citation easier to understand and debug. LangChain may become useful later when the project needs complex retrievers, query rewrite, reranking, multi-query search, or easier vector database switching.

