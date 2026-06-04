# Limitations And Roadmap

The current project is suitable for learning and small-scale personal knowledge bases.

SQLite is transparent, simple, and easy to debug. It is not the best choice for very large semantic search workloads. When the number of chunks grows significantly, search becomes slow, complex metadata filters are needed, or multi-user isolation becomes important, the project can consider Chroma, Qdrant, sqlite-vec, or another vector database.

The current system is designed around a single local login account. It does not currently implement multi-user knowledge-base permission isolation.

The current system does not implement query rewrite. User questions are searched directly.

The current system does not use a rerank model. A future RAG pipeline can first retrieve many candidate chunks and then use a reranker or model-based relevance check to select the best evidence.

The current system does not support WeChat QR-code login. It uses username and password login.

