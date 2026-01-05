"""
Media Analysis Node - AI-powered media organization and analysis
Adapted from nodeo for Loom
"""
import os
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime

from .services.llava_client import LLaVAClient
from .services.template_parser import TemplateParser

logger = logging.getLogger(__name__)


class MediaAnalysisNode:
    """
    Media analysis node that provides AI-powered image analysis and file organization
    
    This node can be used:
    1. Directly (current implementation) - call methods directly
    2. As part of event-driven architecture (future) - processes events from event bus
    
    Features:
    - AI-powered image analysis using LLaVA
    - Metadata extraction (tags, descriptions, scenes)
    - Template-based file renaming
    - Batch processing
    """

    def __init__(
        self,
        ollama_host: str = None,
        ollama_model: str = "llava",
        data_dir: str = "/data"
    ):
        """
        Initialize media analysis node

        Args:
            ollama_host: Ollama API host (defaults to env or Loom default)
            ollama_model: Ollama model name (default: llava)
            data_dir: Data directory for media storage
        """
        # Get Ollama host from env or use default
        if ollama_host is None:
            ollama_host = os.getenv("OLLAMA_URL", "http://192.168.50.157:11434")

        self.llava_client = LLaVAClient(
            host=ollama_host,
            model=ollama_model
        )
        self.data_dir = Path(data_dir)
        self.media_dir = self.data_dir / "media"
        self.media_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"MediaAnalysisNode initialized with Ollama at {ollama_host}")

    async def analyze_image(
        self,
        image_path: str,
        detailed: bool = False
    ) -> Dict[str, Any]:
        """
        Analyze a single image and extract metadata

        Args:
            image_path: Path to image file
            detailed: If True, use detailed analysis prompt

        Returns:
            Dict with analysis results:
            {
                'description': str,
                'tags': List[str],
                'objects': List[str],
                'scene': str,
                'mood': str (optional),
                'colors': List[str] (optional)
            }
        """
        try:
            path = Path(image_path)
            if not path.exists():
                raise FileNotFoundError(f"Image not found: {image_path}")

            metadata = await self.llava_client.extract_metadata(str(path))

            return {
                'success': True,
                'image_path': str(path),
                'metadata': metadata
            }

        except Exception as e:
            logger.error(f"Error analyzing image {image_path}: {e}")
            return {
                'success': False,
                'image_path': image_path,
                'error': str(e)
            }

    async def analyze_batch(
        self,
        image_paths: List[str],
        max_concurrent: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Analyze multiple images in batch

        Args:
            image_paths: List of image file paths
            max_concurrent: Maximum concurrent analyses

        Returns:
            List of analysis results
        """
        try:
            results = await self.llava_client.batch_analyze(
                image_paths,
                extract_full_metadata=True,
                max_concurrent=max_concurrent
            )

            return [
                {
                    'success': 'error' not in result,
                    'image_path': result.get('image_path'),
                    'metadata': {k: v for k, v in result.items() if k != 'image_path' and k != 'error'},
                    'error': result.get('error')
                }
                for result in results
            ]

        except Exception as e:
            logger.error(f"Error in batch analysis: {e}")
            return [
                {
                    'success': False,
                    'image_path': path,
                    'error': str(e)
                }
                for path in image_paths
            ]

    def generate_filename(
        self,
        template: str,
        metadata: Dict[str, Any],
        index: int = 1
    ) -> str:
        """
        Generate filename using template and metadata

        Args:
            template: Template string (e.g., "{description}_{date}_{index}")
            metadata: Metadata dict with analysis results
            index: Sequential index for batch operations

        Returns:
            Generated filename (without extension)
        """
        try:
            parser = TemplateParser(template)
            filename = parser.apply(metadata, index=index)
            return filename
        except Exception as e:
            logger.error(f"Error generating filename: {e}")
            return f"error_{index}"

    def preview_filenames(
        self,
        template: str,
        metadata_list: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Preview filenames for multiple images before renaming

        Args:
            template: Template string
            metadata_list: List of metadata dicts

        Returns:
            List of previews with original and proposed filenames
        """
        parser = TemplateParser(template)
        previews = []

        for idx, metadata in enumerate(metadata_list, start=1):
            try:
                original_filename = metadata.get('original_filename', 'unknown')
                proposed_filename = parser.apply(metadata, index=idx)
                previews.append({
                    'index': idx,
                    'original_filename': original_filename,
                    'proposed_filename': proposed_filename,
                    'metadata': metadata
                })
            except Exception as e:
                logger.error(f"Error generating preview for item {idx}: {e}")
                previews.append({
                    'index': idx,
                    'original_filename': metadata.get('original_filename', 'unknown'),
                    'proposed_filename': f"error_{idx}",
                    'error': str(e)
                })

        return previews

    async def health_check(self) -> Dict[str, Any]:
        """
        Check node health and connectivity

        Returns:
            Health status dict
        """
        try:
            # Try to connect to Ollama
            # Simple health check - could be improved
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                ollama_url = self.llava_client.host.replace('http://', '').replace('https://', '')
                if ':' in ollama_url:
                    host, port = ollama_url.split(':')
                else:
                    host, port = ollama_url, '11434'
                
                # Try to reach Ollama
                response = await client.get(f"{self.llava_client.host}/api/tags", timeout=5.0)
                ollama_status = "ok" if response.status_code == 200 else "error"
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            ollama_status = "error"

        return {
            'node': 'media-analysis',
            'status': 'healthy' if ollama_status == 'ok' else 'degraded',
            'ollama': ollama_status,
            'ollama_host': self.llava_client.host,
            'ollama_model': self.llava_client.model,
            'data_dir': str(self.data_dir),
            'media_dir': str(self.media_dir)
        }

    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get node capabilities and supported features

        Returns:
            Capabilities dict
        """
        return {
            'node_id': 'media-analysis-001',
            'node_type': 'reason',  # AI/LLM processing node
            'name': 'Media Analysis Node',
            'description': 'AI-powered media organization and analysis using LLaVA',
            'version': '1.0.0',
            'capabilities': [
                'image_analysis',
                'metadata_extraction',
                'template_based_renaming',
                'batch_processing'
            ],
            'supported_formats': ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff'],
            'template_variables': [
                'description', 'tags', 'scene', 'date', 'time', 'index',
                'width', 'height', 'orientation', 'original_filename'
            ]
        }

