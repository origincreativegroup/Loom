"""
Template parser for custom file naming patterns
Adapted from nodeo for Loom
"""
import re
import os
import uuid
import random
import string
from datetime import datetime
from typing import Dict, Any
from pathlib import Path


class TemplateParser:
    """
    Parse and apply naming templates to images

    Supported variables:
        Basic Variables:
        {description} - AI-generated description (first N words)
        {tags} - Top tags joined with underscores
        {scene} - Scene type (indoor, outdoor, etc.)
        {date} - Current date (YYYYMMDD)
        {time} - Current time (HHMMSS)
        {datetime} - Combined datetime (YYYYMMDD_HHMMSS)
        {index} - Sequential index
        {original} - Original filename (without extension)

        Date/Time Variables:
        {year} - Year (YYYY)
        {month} - Month (MM)
        {day} - Day (DD)
        {hour} - Hour (HH)
        {minute} - Minute (MM)
        {second} - Second (SS)

        Media Metadata Variables:
        {width} - Media width in pixels
        {height} - Media height in pixels
        {resolution} - width x height combination
        {duration_s} - Media duration in seconds
        {frame_rate} - Frames per second
        {codec} - Video codec or image compression
        {format} - Container/format (e.g., mp4, jpeg)
        {media_type} - Media type (image or video)
        {orientation} - portrait, landscape, or square

        File Metadata Variables:
        {file_size} - File size in MB (e.g., 2_5mb)
        {file_size_kb} - File size in KB (e.g., 2560kb)
        {created_date} - File creation date (YYYYMMDD)
        {modified_date} - File modification date (YYYYMMDD)
        {extension} - Original file extension (without dot)

        AI Analysis Variables:
        {primary_color} - Primary/dominant color detected
        {dominant_object} - Main object in image
        {mood} - Detected mood or atmosphere
        {style} - Detected visual style

        Project-Aware Variables:
        {project} - Project slug (e.g., acme-rebrand-2025)
        {project_name} - Full project name
        {client} - Client name from portfolio metadata
        {project_type} - Project type (client, personal, commercial, etc.)
        {project_number} - Sequential asset number within project (001, 002, ...)

        Utility Variables:
        {random} - Random 8-character string (for uniqueness)
        {random4} - Random 4-character string
        {uuid} - Short UUID (first 8 characters)
    """

    VARIABLE_PATTERN = re.compile(r'\{([^}]+)\}')

    def __init__(self, template: str):
        """
        Initialize parser with template

        Args:
            template: Template string (e.g., "{description}_{date}_{index}")
        """
        self.template = template
        self.variables = self._extract_variables()

    def _extract_variables(self) -> list:
        """Extract variable names from template"""
        return self.VARIABLE_PATTERN.findall(self.template)

    def _sanitize(self, text: str, max_length: int = 50) -> str:
        """Sanitize text for filename use"""
        # Convert to lowercase
        text = text.lower()
        # Replace spaces with underscores
        text = text.replace(' ', '_')
        # Remove special characters
        text = re.sub(r'[^a-z0-9_-]', '', text)
        # Remove multiple underscores
        text = re.sub(r'_+', '_', text)
        # Trim length
        if len(text) > max_length:
            text = text[:max_length].rstrip('_')
        return text

    def _get_description_slug(self, description: str, word_count: int = 4) -> str:
        """Convert description to filename-safe slug"""
        if not description:
            return "untitled"
        words = description.split()[:word_count]
        slug = '_'.join(words)
        return self._sanitize(slug)

    def _get_tags_slug(self, tags: list, count: int = 3) -> str:
        """Convert tags to filename-safe slug"""
        if not tags:
            return ""
        top_tags = tags[:count]
        return self._sanitize('_'.join(top_tags))

    def _get_file_size_mb(self, file_path: str) -> str:
        """Get file size in MB formatted for filename"""
        if not file_path or not os.path.exists(file_path):
            return ""
        try:
            size_bytes = os.path.getsize(file_path)
            size_mb = size_bytes / (1024 * 1024)
            if size_mb < 1:
                return f"{int(size_mb * 10) / 10}mb".replace('.', '_')
            return f"{int(size_mb)}mb"
        except Exception:
            return ""

    def _get_file_size_kb(self, file_path: str) -> str:
        """Get file size in KB formatted for filename"""
        if not file_path or not os.path.exists(file_path):
            return ""
        try:
            size_bytes = os.path.getsize(file_path)
            size_kb = int(size_bytes / 1024)
            return f"{size_kb}kb"
        except Exception:
            return ""

    def _get_file_date(self, file_path: str, stat_type: str = 'created') -> str:
        """Get file creation or modification date (YYYYMMDD)"""
        if not file_path or not os.path.exists(file_path):
            return ""
        try:
            stat = os.stat(file_path)
            if stat_type == 'created':
                timestamp = stat.st_ctime
            else:  # modified
                timestamp = stat.st_mtime
            return datetime.fromtimestamp(timestamp).strftime('%Y%m%d')
        except Exception:
            return ""

    def _get_orientation(self, width: int, height: int) -> str:
        """Determine image orientation"""
        if not width or not height:
            return ""
        if width > height:
            return "landscape"
        elif height > width:
            return "portrait"
        else:
            return "square"

    def _generate_random_string(self, length: int = 8) -> str:
        """Generate random alphanumeric string"""
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choice(chars) for _ in range(length))

    def _generate_short_uuid(self) -> str:
        """Generate short UUID (first 8 characters)"""
        return str(uuid.uuid4())[:8]

    def apply(
        self,
        metadata: Dict[str, Any],
        index: int = 1,
        current_time: datetime = None
    ) -> str:
        """
        Apply template to generate filename

        Args:
            metadata: Image metadata dict
            index: Sequential index for batch operations
            current_time: Datetime to use (defaults to now)

        Returns:
            Generated filename (without extension)
        """
        if current_time is None:
            current_time = datetime.now()

        # Prepare variable replacements
        width = metadata.get('width')
        height = metadata.get('height')
        file_path = metadata.get('file_path', '')

        # Extract project metadata
        project_slug = metadata.get('project', '')
        project_name = metadata.get('project_name', '')
        client = metadata.get('client', '')
        project_type = metadata.get('project_type', '')
        project_number = metadata.get('project_number', 1)

        replacements = {
            # Basic variables
            'description': self._get_description_slug(
                metadata.get('description', ''), word_count=4
            ),
            'tags': self._get_tags_slug(
                metadata.get('tags', []), count=3
            ),
            'scene': self._sanitize(metadata.get('scene', '')),
            'index': str(index).zfill(3),
            'original': self._sanitize(
                Path(metadata.get('original_filename', 'unknown')).stem
            ),

            # Date/time variables
            'date': current_time.strftime('%Y%m%d'),
            'time': current_time.strftime('%H%M%S'),
            'datetime': current_time.strftime('%Y%m%d_%H%M%S'),
            'year': current_time.strftime('%Y'),
            'month': current_time.strftime('%m'),
            'day': current_time.strftime('%d'),
            'hour': current_time.strftime('%H'),
            'minute': current_time.strftime('%M'),
            'second': current_time.strftime('%S'),

            # Media metadata variables
            'width': str(width or ''),
            'height': str(height or ''),
            'resolution': f"{width or ''}x{height or ''}",
            'orientation': self._get_orientation(width, height),
            'duration_s': self._format_numeric(metadata.get('duration_s')),
            'frame_rate': self._format_numeric(metadata.get('frame_rate')),
            'codec': self._sanitize(str(metadata.get('codec', ''))),
            'format': self._sanitize(str(metadata.get('format', ''))),
            'media_type': self._sanitize(str(metadata.get('media_type', ''))),

            # File metadata variables
            'file_size': self._get_file_size_mb(file_path),
            'file_size_kb': self._get_file_size_kb(file_path),
            'created_date': self._get_file_date(file_path, 'created'),
            'modified_date': self._get_file_date(file_path, 'modified'),
            'extension': self._sanitize(Path(metadata.get('original_filename', '')).suffix.lstrip('.')),

            # AI analysis variables
            'primary_color': self._sanitize(metadata.get('primary_color', '')),
            'dominant_object': self._sanitize(metadata.get('dominant_object', '')),
            'mood': self._sanitize(metadata.get('mood', '')),
            'style': self._sanitize(metadata.get('style', '')),

            # Project-aware variables
            'project': self._sanitize(project_slug),
            'project_name': self._sanitize(project_name),
            'client': self._sanitize(client),
            'project_type': self._sanitize(project_type),
            'project_number': str(project_number).zfill(3),

            # Utility variables
            'random': self._generate_random_string(8),
            'random4': self._generate_random_string(4),
            'uuid': self._generate_short_uuid(),
        }

        # Apply replacements
        filename = self.template
        for var, value in replacements.items():
            filename = filename.replace(f'{{{var}}}', value)

        # Clean up any remaining empty patterns or multiple underscores
        filename = re.sub(r'_+', '_', filename)
        filename = filename.strip('_-')

        # Final sanitization
        filename = self._sanitize(filename, max_length=100)

        return filename

    def _format_numeric(self, value: Any) -> str:
        """Format numeric metadata for safe filename insertion."""
        if value is None or value == "":
            return ""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return self._sanitize(str(value))

        text = f"{number:.3f}".rstrip('0').rstrip('.')
        if '.' in text:
            text = text.replace('.', '_')
        return text

    @staticmethod
    def validate_template(template: str) -> tuple[bool, str]:
        """
        Validate a template string

        Args:
            template: Template string to validate

        Returns:
            (is_valid, error_message)
        """
        if not template or template.strip() == "":
            return False, "Template cannot be empty"

        # Check for valid variable syntax
        try:
            parser = TemplateParser(template)
            variables = parser.variables

            # Check for unknown variables
            valid_vars = {
                'description', 'tags', 'scene', 'index', 'original',
                'date', 'time', 'datetime', 'year', 'month', 'day',
                'hour', 'minute', 'second',
                'width', 'height', 'resolution', 'orientation',
                'duration_s', 'frame_rate', 'codec', 'format', 'media_type',
                'file_size', 'file_size_kb', 'created_date', 'modified_date', 'extension',
                'primary_color', 'dominant_object', 'mood', 'style',
                'project', 'project_name', 'client', 'project_type', 'project_number',
                'random', 'random4', 'uuid',
            }
            unknown = set(variables) - valid_vars
            if unknown:
                return False, f"Unknown variables: {', '.join(unknown)}"

            # Test with dummy data
            dummy_metadata = {
                'description': 'test image',
                'tags': ['test', 'sample'],
                'scene': 'indoor',
                'original_filename': 'test.jpg',
                'file_path': '',
                'width': 1920,
                'height': 1080,
            }
            result = parser.apply(dummy_metadata)

            if not result or result.strip() == "":
                return False, "Template produces empty filename"

            return True, "Valid template"

        except Exception as e:
            return False, f"Invalid template: {str(e)}"


# Predefined templates
PREDEFINED_TEMPLATES = {
    "descriptive": "{description}_{date}",
    "detailed": "{description}_{tags}_{datetime}",
    "simple": "{description}_{index}",
    "tagged": "{tags}_{scene}_{date}",
    "dated": "{date}_{time}_{description}",
    "indexed": "{index}_{description}",
    "scene_based": "{scene}_{tags}_{date}",
    "original_preserved": "{original}_{description}_{date}",
}

