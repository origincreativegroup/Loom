# Loom Nodes

Composable intelligence modules for the Loom platform.

## Architecture

Nodes are self-contained modules that provide specific capabilities. They can be used:
1. **Directly** - Import and use in your code
2. **Via Event Bus** (future) - Subscribe to events and emit results

## Available Nodes

### Media Analysis Node

AI-powered media organization and analysis using LLaVA.

- Location: `nodes/media/`
- Features: Image analysis, metadata extraction, template-based renaming
- See `nodes/media/README.md` for details

## Adding New Nodes

1. Create a new directory under `nodes/`
2. Implement node class with:
   - `health_check()` method
   - `get_capabilities()` method (optional)
   - Node-specific functionality
3. Export from `nodes/__init__.py`
4. Update this README

## Future: Event-Driven Architecture

When the event bus architecture is implemented, nodes will:
- Subscribe to event types
- Process events and emit results
- Follow node contracts (see DEVELOPMENT-PLAN.md)

