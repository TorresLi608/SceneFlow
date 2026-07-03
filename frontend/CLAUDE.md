@AGENTS.md

## assistant-ui

This project uses assistant-ui for chat interfaces.

Documentation: https://www.assistant-ui.com/llms-full.txt

MCP docs server: `assistant-ui` from `npx -y @assistant-ui/mcp-docs-server`. Use it before changing assistant-ui APIs or patterns.

Key patterns:
- Use AssistantRuntimeProvider at the app root
- Thread component for full chat interface
- AssistantModal for floating chat widget
- useChatRuntime hook with AI SDK transport
