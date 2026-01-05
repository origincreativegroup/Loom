# Media Analysis Node

AI-powered media organization and analysis node adapted from nodeo for Loom.

## Features

- **AI Image Analysis**: Uses LLaVA via Ollama to analyze images and extract metadata
- **Metadata Extraction**: Extracts descriptions, tags, objects, scenes, and more
- **Template-based Renaming**: Intelligent file renaming using flexible templates
- **Batch Processing**: Process multiple images concurrently

## Usage

### Direct Usage

```python
from nodes.media import MediaAnalysisNode

# Initialize node
node = MediaAnalysisNode(
    ollama_host="http://192.168.50.157:11434",
    ollama_model="llava",
    data_dir="/data"
)

# Analyze a single image
result = await node.analyze_image("/path/to/image.jpg")
print(result['metadata'])

# Analyze multiple images
results = await node.analyze_batch([
    "/path/to/image1.jpg",
    "/path/to/image2.jpg"
])

# Generate filename using template
metadata = {
    'description': 'sunset over mountains',
    'tags': ['sunset', 'mountains', 'landscape'],
    'scene': 'outdoor',
    'original_filename': 'IMG_1234.jpg',
    'date': '20250101'
}
filename = node.generate_filename(
    template="{description}_{date}_{index}",
    metadata=metadata,
    index=1
)
```

### Integration with Loom API

The node can be integrated into Loom's FastAPI application:

```python
from nodes.media import MediaAnalysisNode

# Initialize in your app startup
media_node = MediaAnalysisNode()

@app.post("/api/media/analyze")
async def analyze_media(image_path: str):
    result = await media_node.analyze_image(image_path)
    return result
```

## Configuration

The node uses these environment variables (or defaults):

- `OLLAMA_URL`: Ollama API endpoint (default: `http://192.168.50.157:11434`)
- Model: `llava` (default)

## Template Variables

Supported template variables include:

- `{description}` - AI-generated description
- `{tags}` - Top tags joined with underscores
- `{scene}` - Scene type (indoor, outdoor, etc.)
- `{date}` - Current date (YYYYMMDD)
- `{time}` - Current time (HHMMSS)
- `{index}` - Sequential index
- `{width}`, `{height}` - Image dimensions
- `{original_filename}` - Original filename

See `services/template_parser.py` for the full list of supported variables.

## Health Check

```python
health = await node.health_check()
# Returns status of node and Ollama connection
```

## Capabilities

```python
capabilities = node.get_capabilities()
# Returns node capabilities and supported features
```

