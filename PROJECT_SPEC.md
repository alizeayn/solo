# Voice-First AI Workspace — MVP Project Specification

**Document status:** Initial implementation specification  
**Version:** 0.1  
**Primary goal:** Build the smallest useful, polished, deployable MVP that can be tested on a Linux server and extended without rewriting its core.

---

## 1. Product Vision

Build a single-user, browser-based AI workspace for working on a software project through real-time voice, text, and file input. The user should be able to open or upload a project, send a coding task to a coding agent, observe meaningful progress, ask questions while work is running, and give additional instructions without returning to a terminal.

The first release is a personal MVP, not a commercial multi-tenant product. Optimize for fast delivery, reliability, a clean user experience, and clear module boundaries. Do not build a generalized agent platform before the basic workflow works end to end.

### Core user journey

1. Install and start the app on a Linux server with one setup command.
2. Open the app in a browser on a configurable port and sign in.
3. Configure OpenRouter, ElevenLabs, and the coding agent/provider from the Settings UI.
4. Create a workspace or upload a ZIP archive of an existing project.
5. Start a real-time voice conversation, or type a message / attach a file.
6. Ask the coding agent to inspect or change the selected project.
7. See high-level activity, changed files, test status, errors, and concise progress summaries.
8. Ask a project-specific question while coding is in progress. The system should answer from relevant current state and project context without needlessly interrupting the coding task.
9. Give a follow-up instruction. The system should associate it with the correct task and steer the active coding-agent session when appropriate.
10. Inspect the final summary and task history in the Workspace.

## 2. Scope: Build This First

### Required for MVP

- A polished, responsive dark-themed browser UI.
- A Dockview-based tiled Workspace with three initial panels.
- A FastAPI backend and React + TypeScript frontend served from one public app origin/port.
- A persistent SQLite database for conversations, task state, and event history.
- Pi Coding Agent integration through its supported RPC interface (usually the `pi` CLI). The user has also referred to it informally as “PyAgent/PiAgent”; verify the intended tool and its official current installation instructions before installing anything. Do not silently substitute an unrelated package called `PyAgent`.
- OpenRouter integration for intent routing, context preparation, project questions, and concise progress summarization.
- ElevenLabs Conversational AI WebSocket integration for live voice conversations.
- ElevenLabs TTS for short, proactive progress announcements, with a queue to prevent audio overlap.
- A Settings view where the user can enter and test API credentials, agent ID, model/provider choices, and related options.
- Open Project / Upload Project: create a workspace or upload a ZIP archive into an application-managed workspace directory.
- A first-run setup experience and basic single-user authentication. Do not expose an unauthenticated web interface that can execute code or reveal credentials.
- A one-command installer/bootstrap script and repeatable server deployment, preferably using Docker Compose.
- Health checks, useful logs with secrets redacted, and basic automated tests.

### Explicitly out of scope for the first MVP

- Multi-user accounts, teams, roles, billing, or a SaaS control plane.
- A public plugin marketplace or a generic workflow engine.
- Multiple coding agents editing the same project concurrently.
- Advanced long-term semantic memory, vector databases, and embeddings.
- Image generation, unless it can be added as a small independent artifact tool after the core path works.
- A full IDE or source-code editor. The UI should monitor and coordinate the coding agent, not recreate VS Code.
- A distributed microservice architecture.
- Automatic execution of arbitrary user-uploaded project setup scripts during extraction or project import.

Build extension points for later features, but do not implement out-of-scope items merely to make the architecture appear more sophisticated.

## 3. Architecture Principles

### 3.1 Modular monolith first

Use one backend application with clearly separated modules. Keep the deployment simple and avoid multiple independently deployed services for the MVP. The React app should be built to static assets and served by the backend or by the same-origin web server so only one user-facing port is required.

### 3.2 Core logic must not depend on one provider

The Orchestrator communicates through internal contracts and adapters, not directly against provider-specific APIs throughout the codebase.

Initial adapters:

- `PiCodingAgentAdapter`
- `OpenRouterAdapter`
- `ElevenLabsConversationAdapter`
- `ElevenLabsTTSAdapter`

Do not over-engineer a dynamic plugin loader. Simple Python interfaces / protocols and explicit configuration are sufficient for MVP. Provider-specific details belong inside adapters.

### 3.3 Backend owns task state

The backend is the source of truth for task IDs, task status, event history, active project, and relationships between user messages and tasks. React panel state must never be the authoritative task state.

Closing, moving, resizing, or hiding a Dockview panel must not stop or change the task it displays.

### 3.4 Event-driven progress, not raw log dumping

Consume coding-agent events and normalize them into application-level events. Store relevant events and update the current task state. Do not send every raw log line or every token to the LLM or voice stream.

Use a bounded context snapshot and invoke OpenRouter only for meaningful milestones, errors, task completion, user questions, or explicit requests. Add throttling/debouncing to avoid excessive calls and repetitive announcements.

### 3.5 One active modifying coding task per project for MVP

Allow one active coding operation per selected project to prevent conflicting file edits. Independent read-only questions and context retrieval may run alongside it if they do not modify files. Do not implement unrestricted parallel coding.

---

## 4. Recommended Technology Stack

- **Backend:** Python 3.12+ (or a currently supported stable Python version), FastAPI, Pydantic, asyncio.
- **Frontend:** React, TypeScript, Vite.
- **Tiling UI:** `dockview-react`.
- **Realtime app events:** WebSocket between browser and FastAPI.
- **Persistent state:** SQLite for the single-user MVP. Put database access behind repositories so a later PostgreSQL migration does not require rewriting business logic.
- **Coding agent:** Pi Coding Agent running as a managed long-lived RPC subprocess.
- **Orchestration LLM:** OpenRouter Chat Completions API; use structured, schema-validated output for routing/classification where appropriate.
- **Voice:** ElevenLabs Conversational AI WebSocket for the live conversation; use a backend-generated short-lived signed URL when supported/required, so the ElevenLabs API key never reaches the browser.
- **Progress speech:** ElevenLabs TTS, generated server-side and delivered to the UI through an authenticated endpoint/WebSocket.
- **Deployment:** Docker Compose on a Linux server, persistent volume(s), single exposed application port. Provide a non-Docker development workflow too.

Use current official documentation and pin compatible versions. Do not guess package names, RPC commands, model IDs, or ElevenLabs event formats. Verify them during implementation and document any material limitation.

Official references to verify during implementation:

- Pi CLI integration: https://pi.dev/docs/latest/cli-integration
- Pi RPC mode: https://pi.dev/docs/latest/rpc
- Pi RPC commands: https://pi.dev/docs/latest/rpc-commands
- OpenRouter API: https://openrouter.ai/docs/api-reference/chat/send-chat-completion-request
- ElevenLabs WebSocket: https://elevenlabs.io/docs/eleven-agents/libraries/web-sockets
- ElevenLabs WebSocket event reference: https://elevenlabs.io/docs/eleven-agents/api-reference/eleven-agents/websocket
- ElevenLabs TTS streaming: https://elevenlabs.io/docs/eleven-api/guides/how-to/websockets/realtime-tts
- Dockview: https://dockview.dev/docs/core/overview/

---

## 5. UI / UX Requirements

Design language: modern, polished, restrained dark UI; clear hierarchy; minimal visual noise; responsive layout. Avoid making the workspace look like a raw terminal or a log viewer.

### 5.1 Header

The header should contain:

- Product/app name.
- Current project selector and an **Open Project** action.
- Workspace/layout control where practical.
- Global task status (for example, “1 task running”).
- A Settings action and connection-status indicators for OpenRouter, ElevenLabs, and Pi.

### 5.2 Initial Dockview layout: three panels

**Panel A — Conversation (primary panel)**

- Voice start/stop control and clear listening/speaking/connecting indicators.
- Live transcription and assistant transcript/history.
- Text input as an equal fallback to voice.
- File attachment control for images and text/document files where supported.
- Project/task context indicator so the user understands which project or task the message targets.
- Visible error/reconnect states.

**Panel B — Coding Agent Activity (monitor panel)**

- Current task and status.
- High-level activity timeline: inspecting files, editing, running tests, investigating an error, completing work.
- Changed file list and test result summary when available.
- Recent meaningful tool actions and safe error excerpts.
- Concise progress summaries.
- Do not expose private internal chain-of-thought. Show observable tool activity and concise, user-facing explanations instead.
- This is primarily a monitor, not a second terminal/chat UI.

**Panel C — Inspector / Artifacts (initially passive)**

- An empty state when no artifact or selected detail exists.
- Show selected task details, a relevant file excerpt, a generated diagram, a summary, or another artifact when requested/available.
- It may be opened, hidden, resized, tabbed, or moved using Dockview.
- Do not implement image generation in the critical path. Keep this panel generic enough to support it later.

### 5.3 Dockview behavior

- Users can resize, drag, tab, split, and rearrange panels using Dockview.
- Persist the layout in browser local storage for the current single user.
- Restore a safe default layout if stored layout JSON is invalid or from an incompatible version.
- Panel visibility/layout is independent from backend task lifecycle.
- On smaller screens, fall back to tabs or a stacked layout rather than forcing unusable tiny tiles.

### 5.4 Settings UI

Provide a small setup/settings screen with status badges and a “Test connection” action where practical.

**OpenRouter settings**
- API key.
- Model ID as a configurable text field with a sensible example/default, not a hard-coded assumption.
- Test the key and display a useful error without exposing the secret.

**ElevenLabs settings**
- API key.
- Conversational Agent ID.
- TTS voice ID or another provider-supported voice selector where necessary for progress speech.
- Test configuration and show the actual connection/configuration status.

**Coding agent settings**
- Provider/model configuration supported by the installed Pi version.
- Provider/model ID fields.
- Provider API key or supported credential option.
- If Pi is configured to use OpenRouter, offer an explicit “Reuse the OpenRouter key” option instead of requiring the same key to be entered twice.
- Optional base URL only when supported by the provider/Pi configuration.
- Show the installed Pi version and whether RPC can start successfully.
- Provider/model changes apply to new agent sessions unless the installed tool explicitly supports safe changes to a running session.

Do not build a complete model marketplace or an elaborate provider discovery workflow. Use a concise provider selector plus a model ID field and validate through the actual provider/runtime.

### 5.5 Secret handling

- API keys are submitted directly to backend endpoints over the same authenticated origin.
- Never return complete stored secrets to the UI; return only configured/masked status.
- Never log API keys, signed URLs, passwords, auth cookies, or complete environment dumps.
- Store secrets server-side only, encrypted at rest where practical, with the encryption key stored separately from encrypted records or in a restricted persistent secrets file.
- Apply restrictive file permissions to configuration, database, and secret files.
- Add an option to replace/delete a configured key.

---

## 6. Project / Workspace Management

The MVP must not allow a browser user to select arbitrary server filesystem paths.

- Store projects under a configured application-managed directory, for example `/data/workspaces/`.
- Support creating a new empty project/workspace.
- Support uploading a `.zip` project archive and extracting it into the managed directory.
- Support listing and opening projects previously created/imported by the app.
- Provide configurable upload-size limits and useful validation errors.
- Protect ZIP extraction against path traversal (Zip Slip), absolute paths, unsafe symlinks, and overwriting files outside the target workspace.
- Do not execute scripts or dependency installation commands automatically during upload.
- The selected project root is the working directory provided to Pi.
- Ensure project files and task history survive container recreation through persistent volumes.
- For the first MVP, one selected project is active in the workspace at a time.

---

## 7. Orchestration and State Management

### 7.1 Task model

Each task should at minimum store:

- `task_id`
- `project_id`
- `conversation_id` or `session_id`
- optional `parent_task_id`
- `task_type` (coding, question, context lookup, etc.)
- `status`
- user request / normalized instruction
- current concise progress summary
- related file paths
- result summary and safe error information
- coding-agent session/process reference where applicable
- created/updated/completed timestamps

Use explicit statuses such as:

`QUEUED`, `RUNNING`, `WAITING_FOR_INPUT`, `PAUSE_REQUESTED`, `PAUSED`, `CANCEL_REQUESTED`, `CANCELLED`, `COMPLETED`, `FAILED`, and `RECOVERY_REQUIRED`.

Do not mark a task `PAUSED` or `CANCELLED` merely because a command was sent. Wait for the actual adapter/runtime to confirm the resulting state. If the external process is lost, mark the task for recovery/inspection rather than assuming it completed.

### 7.2 Event model

Persist normalized events with at least:

- `event_id`
- `task_id` when relevant
- event type
- timestamp
- concise display message
- structured safe metadata
- optional reference to raw diagnostic output stored separately

Normalize Pi events such as run start/end, tool execution start/update/end, file changes, and final settlement into a small application event vocabulary. Keep protocol parsing inside `PiCodingAgentAdapter`.

Store enough raw diagnostic detail for debugging, but do not send raw logs wholesale to the conversation model. Set reasonable retention/size limits for noisy output.

### 7.3 Follow-up requests during an active task

Classify incoming user messages into a small number of supported intents:

- `CHAT_OR_EXPLAIN`: answer a question using the current task snapshot and relevant project context; do not interrupt the coding task by default.
- `STEER_ACTIVE_TASK`: send a follow-up instruction to the active Pi session using the supported RPC steering mechanism.
- `STOP_ACTIVE_TASK`: request cancellation/abort, then update the state only after confirmation.
- `START_CODING_TASK`: create and run a coding task if no conflicting modifying task is active.
- `NEEDS_CLARIFICATION`: ask which task or project the user means.

Use OpenRouter for intent classification when necessary, with a Pydantic-validated structured result. For obvious UI operations, deterministic backend rules may be used instead. Never let unvalidated model output directly execute an arbitrary shell command or filesystem path.

If a new coding request arrives while another modifying task is active, prefer steering the active task or ask the user whether to wait/cancel. Do not silently start a second writer against the same project.

### 7.4 Pi process lifecycle

- Launch Pi as a managed subprocess in its supported RPC mode; consume stdout continuously as JSONL and keep protocol output separate from stderr diagnostics.
- Correlate command responses by request ID.
- Distinguish “prompt accepted” from “task completed”; continue listening for the appropriate settlement event.
- Detect process exit, malformed protocol records, timeout, and broken pipes.
- Shut down subprocesses cleanly when the app stops.
- Do not assume that a generic Python API exists for Pi; use the supported documented integration mechanism for the installed version.

### 7.5 Minimal memory/context

No vector database is required for MVP.

Build a bounded context snapshot from:

- Selected project metadata.
- Active task and status.
- The last user instruction.
- Recent normalized events.
- Changed-file list and concise diff summary if available.
- Pending questions/decisions.
- The most recent task summary.

When the user asks a project-specific question, fetch only relevant data: matching files, bounded file excerpts, recent diffs, or task events. Apply hard limits to file count, file size, and total context tokens/characters. Do not send the entire repository or unbounded logs to an LLM.

Persist the current summary and recent history in SQLite. Long-term semantic memory is deferred.

---

## 8. Voice and Progress Updates

### 8.1 Live voice session

Use the official ElevenLabs Conversational AI WebSocket flow. The browser should obtain any required short-lived signed URL from the backend; the long-lived ElevenLabs API key must remain server-side.

The Settings UI must make it obvious that the Conversational Agent ID is required. If the configured Agent ID is missing or invalid, show a setup message rather than failing silently.

Validate the exact event names and payload formats against current ElevenLabs documentation during implementation. Support live user transcript, agent transcript/response, connection state, errors, and reconnect behavior.

### 8.2 Context updates

OpenRouter prepares a compact project/task summary for the voice conversation. Send it through the supported contextual-update mechanism when the conversation is active, and keep a copy in app state. Context updates should not include entire logs or repository contents.

A contextual update is background context; do not assume it will immediately make ElevenLabs speak. Implement and test the actual behavior rather than treating context injection as proactive speech.

### 8.3 Proactive spoken progress

When a meaningful coding event occurs, create a concise text announcement through OpenRouter or deterministic templates. Use an ElevenLabs TTS voice configured in Settings to speak selected announcements.

Implement a small speech arbiter/queue:

- Announce only meaningful milestones, errors, a needed user decision, or completion.
- Avoid repetitive or low-value narration.
- Do not overlap progress audio with the active conversation audio.
- If the user starts speaking, stop or defer a lower-priority progress announcement as safely as possible.
- Queue noncritical updates while the voice agent is responding; drop stale announcements if a newer status supersedes them.
- Always show the same progress text visually in the UI, so voice can be disabled without losing information.

If independent TTS audio and the Conversational AI WebSocket cannot be coordinated reliably in the first implementation, deliver visible summaries and the context-update path first, then implement the speech queue as a clearly documented next step. Do not claim proactive speech works unless it has been tested end to end.

### 8.4 Reporting cadence

The agent should not narrate every tool call. Prefer short summaries such as:

- “I’m inspecting the module and its tests.”
- “The implementation is in place; one test failed, and I’m investigating why.”
- “The change is complete. The tests passed.”

These are examples, not hard-coded progress assertions. Only announce facts supported by actual events/results.

---

## 9. OpenRouter Responsibilities

Use OpenRouter through a small provider adapter. Keep the model ID configurable in the UI.

For MVP, OpenRouter is responsible for:

1. Intent classification where deterministic rules are insufficient.
2. Transforming normalized coding-agent events into concise, user-facing progress summaries.
3. Preparing bounded context snapshots for the voice session.
4. Answering project-specific questions from retrieved, relevant file snippets and task history.
5. Preparing short speech announcements for the TTS queue.

Do not invoke OpenRouter for every raw Pi event. Aggregate/debounce events and use meaningful triggers. Use timeouts, concise prompts, safe fallbacks, and structured response validation. If OpenRouter is unavailable, the UI should continue displaying raw normalized progress and the user should still be able to inspect task status.

Never allow the router/summarizer model to silently rewrite user instructions or change the selected project. Ask for clarification when intent or target task is ambiguous.

---

## 10. Security and Deployment

### 10.1 Authentication is mandatory

Because the app can run code and edit files, the deployed UI must not be public and unauthenticated.

- Implement simple single-user login for the MVP.
- The installer should generate or request an initial admin password and print/display it securely once. Store only a password hash in app configuration.
- Protect API and WebSocket endpoints with the same session authentication policy, except minimal health/setup endpoints that reveal no secrets.
- Use secure, HttpOnly, SameSite cookies where supported; validate WebSocket authentication.
- Do not enable permissive CORS by default.
- Document that internet-facing deployment should use HTTPS (for example, a reverse proxy with a valid certificate) or a secure tunnel. Do not imply that plain HTTP on a public IP is safe for API-key entry.

### 10.2 Agent execution boundary

- Run the app as a non-root user where practical.
- Keep workspaces under the managed workspaces directory.
- Never accept arbitrary server filesystem paths from the browser.
- Validate all task/project IDs server-side.
- Restrict file operations to the active project root.
- Do not execute uploaded files automatically.
- Treat project content and tool output as untrusted data, not as application instructions.
- Make high-impact operations visible and provide a clear cancel control.

### 10.3 Deployment requirements

Deliver:

- `Dockerfile` and `docker-compose.yml` (or equivalent reproducible deployment files).
- `install.sh` for a straightforward first-time installation on a supported Linux server.
- `.env.example` for non-secret operational settings.
- A persistent data volume for SQLite, configuration/secrets, and workspaces.
- A configurable web port, defaulting to a documented safe value.
- Health endpoint and container restart policy.
- Commands for start, stop, logs, update, backup, and restore.
- Clear failure messages for missing Docker, invalid credentials, provider connection errors, unavailable Pi runtime, and port conflicts.

The installer must be idempotent where practical and must not overwrite existing user configuration or workspace data without explicit confirmation. Do not bake API keys into the Docker image or source repository.

---

## 11. Acceptance Criteria

The MVP is accepted only when all critical-path checks pass on a real Linux server:

1. A new installation can be completed with the documented installer and the app becomes available on the configured port.
2. Authentication is required before viewing the Workspace or using project/coding functionality.
3. The app can configure, test, and safely persist OpenRouter and ElevenLabs credentials, plus Pi provider/model settings.
4. The user can create a project or upload a ZIP archive into the managed workspace safely.
5. The browser can start a voice conversation through ElevenLabs and also send text when voice transcription needs correction.
6. A user can ask for a small code change and the request reaches Pi RPC in the selected project directory.
7. The Activity panel shows meaningful live events from the actual Pi process and reaches a correct terminal task status.
8. During an active coding task, the user can ask a task/project question and receive a concise answer based on relevant state/context without automatically interrupting the coding task.
9. A follow-up coding instruction is associated with the correct active task and uses supported steering or an explicit safe fallback.
10. Task status and recent event history survive app/container restart. On restart, uncertain in-flight tasks are marked for inspection/recovery rather than falsely marked completed.
11. Meaningful progress summaries appear visually. Proactive voice announcements are counted as complete only after overlap/interruption behavior has been tested.
12. Moving or closing a Dockview panel does not stop the corresponding task.
13. API keys and passwords never appear in API responses, application logs, browser local storage, or static frontend bundles.
14. Automated tests cover task-state transitions, credential redaction, ZIP extraction safety, provider-adapter error handling, and core API behavior.
15. A basic end-to-end test proves: user request → Pi coding task → live activity events → follow-up question/instruction → completed result.

---

## 12. Implementation Strategy

Build vertically and validate each step before adding more features:

**Phase 1 — Deployable shell:** FastAPI + React/Vite + Dockview, login, Settings UI, SQLite, health check, Docker Compose, installer.

**Phase 2 — Pi integration:** install/version-check Pi, launch RPC, parse events, submit one task, display activity and persist task state.

**Phase 3 — OpenRouter context layer:** intent routing, bounded context snapshots, task/project Q&A, concise progress summaries, API-key testing.

**Phase 4 — ElevenLabs voice:** authenticated setup, signed URL / official WebSocket flow, live transcript and voice response, text fallback.

**Phase 5 — Live progress UX:** select meaningful events, contextual updates, TTS announcement queue, interruption/overlap handling.

**Phase 6 — End-to-end hardening:** tests, restart recovery, logging/redaction, installer idempotency, deployment documentation, and one real server smoke test.

Do not spend time polishing noncritical features before the end-to-end path works. Prefer simple readable modules and explicit contracts over premature abstractions.

---

## 13. Definition of Done

The MVP is a small, secure single-user AI Workspace that can be installed and tested on a Linux server, opened in a browser, configured without editing source code, connected to a real-time ElevenLabs voice session, and used to send a coding task to Pi. It displays real task activity, preserves state, accepts mid-task questions or follow-up instructions, and gives concise progress feedback without requiring the user to work in the CLI.

The architecture should make later replacement/addition of providers possible through adapters, but the first release needs only one working provider path per capability.
