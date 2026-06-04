# Authentication And SQLite Storage

The project uses username and password login. It does not support WeChat QR-code login.

After a successful login, the backend creates a random session id. The session id is stored in SQLite and sent to the browser as an HttpOnly cookie. Later requests include that cookie, and the backend uses it to identify the current logged-in user.

SQLite stores the following project data:

- users, including usernames and password hashes
- sessions, including random session ids, user ids, and expiration times
- conversations, including conversation titles and update times
- messages, including user messages, assistant messages, and source metadata
- knowledge document metadata
- vector chunks, including document ids, chunk indexes, text snippets, embeddings, and content hashes

The current login system is designed for a local learning project and a single configured account. It is not a WeChat OAuth system and it is not a multi-user identity platform.

