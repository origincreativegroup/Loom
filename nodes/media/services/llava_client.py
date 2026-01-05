"""
LLaVA image analysis client using Ollama
Adapted from nodeo for Loom
"""
import json
import logging
from typing import Dict, List, Optional
import ollama
from pathlib import Path

logger = logging.getLogger(__name__)


class LLaVAClient:
    """Client for LLaVA vision model via Ollama"""

    def __init__(
        self,
        host: str = "http://192.168.50.157:11434",
        model: str = "llava",
        timeout: int = 120
    ):
        self.host = host
        self.model = model
        self.timeout = timeout

    async def analyze_image(
        self,
        image_path: str,
        prompt: str = None,
        detailed: bool = False
    ) -> str:
        """
        Analyze an image using LLaVA

        Args:
            image_path: Path to the image file
            prompt: Custom prompt for analysis (optional)
            detailed: If True, use a more detailed analysis prompt

        Returns:
            Analysis text from LLaVA
        """
        try:
            logger.info(f"Analyzing image: {image_path}")

            client = ollama.Client(host=self.host)

            if prompt is None:
                if detailed:
                    prompt = """Provide a comprehensive analysis of this image:

1. Main Subject: What is the primary focus or subject?
2. Composition: How is the image composed? (framing, perspective, layout)
3. Visual Elements: Key objects, people, or elements visible
4. Setting/Scene: Where does this appear to be? What's the context?
5. Colors and Lighting: Dominant colors, lighting conditions, mood
6. Notable Details: Any interesting or distinctive features

Be specific and descriptive."""
                else:
                    prompt = """Analyze this image and describe:
- What you see (main subjects and objects)
- The scene type and setting
- Notable visual characteristics
- The overall composition and mood

Provide a clear, detailed description in 2-3 sentences."""

            response = client.chat(
                model=self.model,
                messages=[
                    {
                        'role': 'user',
                        'content': prompt,
                        'images': [image_path]
                    }
                ],
                options={
                    'temperature': 0.5,
                    'num_predict': 300 if detailed else 200,
                }
            )

            analysis = response['message']['content'].strip()
            logger.info(f"Analysis completed: {len(analysis)} chars")
            return analysis

        except Exception as e:
            logger.error(f"Error analyzing image {image_path}: {e}")
            raise

    async def extract_metadata(self, image_path: str) -> Dict:
        """
        Extract structured metadata from image using optimized single-call method

        Args:
            image_path: Path to the image file

        Returns:
            {
                'description': str,
                'tags': List[str],
                'objects': List[str],
                'scene': str
            }
        """
        try:
            client = ollama.Client(host=self.host)

            prompt = """Analyze this image in detail and provide a comprehensive analysis in JSON format.

Your response must be valid JSON with these exact keys:
{
  "description": "A detailed 2-3 sentence description covering the main subject, composition, and notable elements",
  "tags": ["array", "of", "5-10", "relevant", "lowercase", "keywords"],
  "objects": ["list", "of", "main", "visible", "objects"],
  "scene": "scene type in 1-2 words",
  "mood": "optional mood/atmosphere descriptor",
  "colors": ["dominant", "color", "palette"]
}

Guidelines:
- Description: Be specific about what makes this image unique. Include composition, subjects, and context.
- Tags: Use semantically relevant, searchable keywords (e.g., "sunset", "architecture", "portrait")
- Objects: List concrete, visible items (e.g., "person", "building", "tree", "car")
- Scene: Choose from: indoor, outdoor, portrait, landscape, urban, nature, abstract, close-up, aerial, street, studio
- Mood: Describe the atmosphere (e.g., "peaceful", "energetic", "moody", "bright")
- Colors: List 2-4 dominant colors (e.g., "blue", "warm tones", "monochrome")

Respond with valid JSON only, no additional text."""

            response = client.chat(
                model=self.model,
                messages=[{
                    'role': 'user',
                    'content': prompt,
                    'images': [image_path]
                }],
                options={
                    'temperature': 0.3,
                    'num_predict': 300,
                }
            )

            content = response['message']['content'].strip()

            # Handle markdown code blocks if present
            if content.startswith('```'):
                lines = content.split('\n')
                json_lines = []
                in_code_block = False
                for line in lines:
                    if line.strip().startswith('```'):
                        in_code_block = not in_code_block
                        continue
                    if in_code_block or (not line.strip().startswith('```')):
                        json_lines.append(line)
                content = '\n'.join(json_lines).strip()

            try:
                metadata = json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON response for {image_path}: {e}")
                logger.debug(f"Raw response: {content}")
                # Fallback: return basic structure
                return {
                    'description': content[:200] if content else 'Analysis failed',
                    'tags': [],
                    'objects': [],
                    'scene': 'unknown'
                }

            # Validate and clean the response
            description = metadata.get('description', '').strip()

            tags = metadata.get('tags', [])
            if isinstance(tags, str):
                tags = [t.strip().lower() for t in tags.split(',') if t.strip()]
            else:
                tags = [str(t).strip().lower() for t in tags if str(t).strip()]

            objects = metadata.get('objects', [])
            if isinstance(objects, str):
                objects = [o.strip() for o in objects.split(',') if o.strip()]
            else:
                objects = [str(o).strip() for o in objects if str(o).strip()]

            scene = metadata.get('scene', '').strip().lower()

            result = {
                'description': description,
                'tags': tags[:10],  # Limit to 10 tags
                'objects': objects[:10],  # Limit to 10 objects
                'scene': scene
            }

            # Add optional fields if present
            mood = metadata.get('mood', '').strip()
            colors = metadata.get('colors', [])
            if isinstance(colors, str):
                colors = [c.strip() for c in colors.split(',') if c.strip()]
            if mood:
                result['mood'] = mood
            if colors:
                result['colors'] = colors[:5]

            return result

        except Exception as e:
            logger.error(f"Error extracting metadata from {image_path}: {e}")
            raise

    async def batch_analyze(
        self,
        image_paths: List[str],
        extract_full_metadata: bool = True,
        max_concurrent: int = 5
    ) -> List[Dict]:
        """
        Analyze multiple images in batch with concurrent processing

        Args:
            image_paths: List of image paths
            extract_full_metadata: If True, extract full metadata; else just description
            max_concurrent: Maximum number of concurrent requests (default: 5)

        Returns:
            List of metadata dicts
        """
        import asyncio

        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_single(image_path: str) -> Dict:
            async with semaphore:
                try:
                    if extract_full_metadata:
                        metadata = await self.extract_metadata(image_path)
                    else:
                        description = await self.analyze_image(image_path)
                        metadata = {'description': description}

                    metadata['image_path'] = image_path
                    return metadata

                except Exception as e:
                    logger.error(f"Failed to analyze {image_path}: {e}")
                    return {
                        'image_path': image_path,
                        'error': str(e)
                    }

        results = await asyncio.gather(
            *[analyze_single(path) for path in image_paths],
            return_exceptions=False
        )

        return results

