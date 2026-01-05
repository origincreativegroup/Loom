"""
Example usage of Media Analysis Node
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from nodes.media import MediaAnalysisNode


async def main():
    """Example usage of the media analysis node"""
    
    # Initialize node
    node = MediaAnalysisNode(
        ollama_host="http://192.168.50.157:11434",
        ollama_model="llava",
        data_dir="/data"
    )
    
    # Check health
    print("Checking node health...")
    health = await node.health_check()
    print(f"Health: {health}")
    print()
    
    # Get capabilities
    print("Node capabilities:")
    capabilities = node.get_capabilities()
    print(f"  Name: {capabilities['name']}")
    print(f"  Type: {capabilities['node_type']}")
    print(f"  Capabilities: {', '.join(capabilities['capabilities'])}")
    print()
    
    # Example: Analyze an image (replace with actual path)
    # image_path = "/path/to/your/image.jpg"
    # print(f"Analyzing image: {image_path}")
    # result = await node.analyze_image(image_path)
    # if result['success']:
    #     print(f"Description: {result['metadata']['description']}")
    #     print(f"Tags: {result['metadata']['tags']}")
    #     print(f"Scene: {result['metadata']['scene']}")
    
    # Example: Generate filename
    metadata = {
        'description': 'sunset over mountains with lake reflection',
        'tags': ['sunset', 'mountains', 'lake', 'landscape', 'nature'],
        'scene': 'outdoor',
        'original_filename': 'IMG_1234.jpg',
        'width': 1920,
        'height': 1080,
    }
    
    template = "{description}_{date}_{index}"
    filename = node.generate_filename(template, metadata, index=1)
    print(f"Generated filename: {filename}")
    print()
    
    print("Media Analysis Node is ready to use!")


if __name__ == "__main__":
    asyncio.run(main())

