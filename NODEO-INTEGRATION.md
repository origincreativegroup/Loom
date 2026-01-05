# nodeo Integration into Loom

This document describes the integration of useful functionality from the nodeo project into Loom as a media analysis node.

## What Was Integrated

The following core functionality from nodeo has been extracted and adapted for Loom:

1. **LLaVA Client** (`nodes/media/services/llava_client.py`)
   - AI-powered image analysis using LLaVA via Ollama
   - Metadata extraction (descriptions, tags, objects, scenes)
   - Batch processing support

2. **Template Parser** (`nodes/media/services/template_parser.py`)
   - Flexible file naming templates
   - Support for 70+ template variables
   - Metadata-aware filename generation

3. **Media Analysis Node** (`nodes/media/node.py`)
   - High-level interface for media analysis
   - Combines LLaVA client and template parser
   - Health checks and capabilities reporting

## Structure

```
nodes/
├── __init__.py
├── README.md
└── media/
    ├── __init__.py
    ├── node.py                    # Main node class
    ├── README.md                  # Node documentation
    ├── example_usage.py          # Usage examples
    └── services/
        ├── __init__.py
        ├── llava_client.py        # LLaVA integration
        └── template_parser.py     # Template parsing engine
```

## Usage

### Basic Usage

```python
from nodes.media import MediaAnalysisNode

# Initialize
node = MediaAnalysisNode(
    ollama_host="http://192.168.50.157:11434",
    ollama_model="llava"
)

# Analyze an image
result = await node.analyze_image("/path/to/image.jpg")
print(result['metadata']['description'])
print(result['metadata']['tags'])

# Generate filename
filename = node.generate_filename(
    template="{description}_{date}_{index}",
    metadata=result['metadata'],
    index=1
)
```

### Integration with Loom API

You can integrate the node into Loom's FastAPI application:

```python
from nodes.media import MediaAnalysisNode

# In your app startup
media_node = MediaAnalysisNode()

@app.post("/api/media/analyze")
async def analyze_media(image_path: str):
    result = await media_node.analyze_image(image_path)
    return result

@app.get("/api/media/health")
async def media_health():
    return await media_node.health_check()
```

## Configuration

The node uses environment variables or defaults:

- `OLLAMA_URL`: Ollama API endpoint (default: `http://192.168.50.157:11434`)
- Model: `llava` (default, can be overridden in constructor)

## Dependencies Added

Added to `app/requirements.txt`:
- `ollama==0.1.6` - Ollama Python client

## Differences from nodeo

1. **No Database Dependencies**: The node works standalone without SQLAlchemy or database models
2. **Simplified Interface**: Focused on core analysis and renaming capabilities
3. **Loom Integration**: Designed to work with Loom's architecture (current and future event-driven)
4. **Self-Contained**: All services are included, no external nodeo dependencies

## Future Enhancements

When Loom's event bus architecture is implemented (see DEVELOPMENT-PLAN.md), this node can:
- Subscribe to filesystem events
- Process media files automatically
- Emit analysis results as events
- Integrate with other nodes in the workspace

## Testing

See `nodes/media/example_usage.py` for usage examples.

## Documentation

- Node documentation: `nodes/media/README.md`
- General nodes documentation: `nodes/README.md`

