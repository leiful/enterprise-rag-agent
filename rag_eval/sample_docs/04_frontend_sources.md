# Frontend Source Display

The frontend supports displaying knowledge-base sources below AI replies.

When the backend returns an answer with sources, the AI reply can show citation labels such as [K1], [K2], and [K3]. The user can expand the source panel below the reply.

Each source panel item displays:

- the source label
- the source document name
- the chunk index
- the retrieval score
- the original text snippet

The source panel helps the user judge whether an AI answer is actually supported by the knowledge base.

Both normal chat and streaming chat preserve source information. Streaming chat returns source metadata in the response header and saves it with the assistant message.

