# Project Overview

This project is a login-protected AI chat and knowledge-base question answering system.

The core features are:

- user login with a server-side session cookie
- normal chat responses
- streaming chat responses
- conversation history
- knowledge-base file upload
- knowledge-base indexing
- knowledge-base search
- knowledge-base document deletion
- RAG answers with source citations

The backend is built with FastAPI. The frontend is built with Vue 3 and Vite. SQLite is used for local storage.

SQLite stores users, sessions, conversations, messages, knowledge document metadata, and knowledge chunks. The project currently uses a small SQLite vector store for learning and small-scale knowledge bases.

The project does not currently use Chroma, Qdrant, Milvus, Pinecone, or LangChain.

