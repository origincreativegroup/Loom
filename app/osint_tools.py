"""
OSINT Tool Integrations for Loom
Provides unified interface to local OSINT tools on pi-net
"""

import asyncio
import json
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime

import httpx
import asyncssh
import docker
from docker.errors import DockerException


# ============================================================================
# Base Tool Interface
# ============================================================================

class OSINTTool(ABC):
    """Base class for all OSINT tool integrations"""

    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled
        self.status = "idle"
        self.results = []
        self.error = None

    @abstractmethod
    async def execute(self, target: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute the tool against a target"""
        pass

    def get_status(self) -> Dict[str, Any]:
        """Get current tool status"""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "status": self.status,
            "results_count": len(self.results),
            "error": self.error
        }


# ============================================================================
# Recon-ng Integration (SSH to pi-core)
# ============================================================================

class ReconNGTool(OSINTTool):
    """Recon-ng integration via SSH"""

    def __init__(self):
        super().__init__("recon-ng")
        self.ssh_host = os.getenv("PICORE_SSH_HOST", "192.168.50.168")
        self.ssh_user = os.getenv("PICORE_SSH_USER", "admin")
        self.ssh_key_path = os.getenv("PICORE_SSH_KEY", "/app/keys/id_ed25519")

    async def execute(self, target: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute Recon-ng via SSH"""
        self.status = "running"
        self.error = None

        try:
            # Default to subdomain enumeration
            module = options.get("module", "recon/domains-hosts/hackertarget") if options else "recon/domains-hosts/hackertarget"

            # Construct Recon-ng command
            commands = [
                f"recon-ng -w {target.replace('.', '_')}",
                f"db insert domains {target}",
                f"modules load {module}",
                "run",
                "show hosts",
                "exit"
            ]

            command = " && ".join(commands)

            # Connect via SSH and execute
            async with asyncssh.connect(
                self.ssh_host,
                username=self.ssh_user,
                client_keys=[self.ssh_key_path] if os.path.exists(self.ssh_key_path) else None,
                known_hosts=None  # Warning: Disables host key verification
            ) as conn:
                result = await conn.run(command, check=False)

                self.results = self._parse_output(result.stdout)
                self.status = "completed"

                return {
                    "tool": self.name,
                    "target": target,
                    "status": "success",
                    "results": self.results,
                    "raw_output": result.stdout,
                    "timestamp": datetime.utcnow().isoformat()
                }

        except Exception as e:
            self.status = "error"
            self.error = str(e)
            return {
                "tool": self.name,
                "target": target,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    def _parse_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse Recon-ng output"""
        results = []
        # Simple parsing - extract hosts from output
        for line in output.split('\n'):
            if '|' in line and not line.startswith('+'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 2 and parts[1]:
                    results.append({
                        "type": "subdomain",
                        "value": parts[1]
                    })
        return results


# ============================================================================
# TheHarvester Integration (Docker)
# ============================================================================

class TheHarvesterTool(OSINTTool):
    """TheHarvester integration via Docker"""

    def __init__(self):
        super().__init__("theharvester")
        try:
            self.docker_client = docker.from_env()
        except DockerException:
            self.enabled = False

    async def execute(self, target: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute TheHarvester in Docker container"""
        self.status = "running"
        self.error = None

        try:
            # Default sources
            sources = options.get("sources", "google,bing,duckduckgo") if options else "google,bing,duckduckgo"

            # Run container
            container = self.docker_client.containers.run(
                "theharvester:latest",
                f"-d {target} -b {sources}",
                remove=True,
                detach=False
            )

            output = container.decode('utf-8')
            self.results = self._parse_output(output, target)
            self.status = "completed"

            return {
                "tool": self.name,
                "target": target,
                "status": "success",
                "results": self.results,
                "raw_output": output,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            self.status = "error"
            self.error = str(e)
            return {
                "tool": self.name,
                "target": target,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    def _parse_output(self, output: str, target: str) -> List[Dict[str, Any]]:
        """Parse TheHarvester output"""
        results = []
        current_section = None

        for line in output.split('\n'):
            if '[*] Emails found:' in line:
                current_section = 'email'
            elif '[*] Hosts found:' in line:
                current_section = 'host'
            elif line.strip() and current_section:
                if '@' in line and current_section == 'email':
                    results.append({"type": "email", "value": line.strip()})
                elif current_section == 'host':
                    results.append({"type": "host", "value": line.strip()})

        return results


# ============================================================================
# Sherlock Integration (Docker)
# ============================================================================

class SherlockTool(OSINTTool):
    """Sherlock integration via Docker"""

    def __init__(self):
        super().__init__("sherlock")
        try:
            self.docker_client = docker.from_env()
        except DockerException:
            self.enabled = False

    async def execute(self, target: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute Sherlock in Docker container"""
        self.status = "running"
        self.error = None

        try:
            # Run container
            container = self.docker_client.containers.run(
                "sherlock/sherlock:latest",
                target,
                remove=True,
                detach=False
            )

            output = container.decode('utf-8')
            self.results = self._parse_output(output, target)
            self.status = "completed"

            return {
                "tool": self.name,
                "target": target,
                "status": "success",
                "results": self.results,
                "raw_output": output,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            self.status = "error"
            self.error = str(e)
            return {
                "tool": self.name,
                "target": target,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    def _parse_output(self, output: str, username: str) -> List[Dict[str, Any]]:
        """Parse Sherlock output"""
        results = []

        for line in output.split('\n'):
            if '[+]' in line:
                # Extract platform and URL
                parts = line.split('[+]')[1].strip().split(':')
                if len(parts) >= 2:
                    platform = parts[0].strip()
                    url = ':'.join(parts[1:]).strip()
                    results.append({
                        "type": "social_media",
                        "platform": platform,
                        "url": url,
                        "username": username
                    })

        return results


# ============================================================================
# SpiderFoot Integration (API)
# ============================================================================

class SpiderFootTool(OSINTTool):
    """SpiderFoot integration via API"""

    def __init__(self):
        super().__init__("spiderfoot")
        self.api_url = os.getenv("SPIDERFOOT_URL", "http://spider.lan")
        self.api_key = os.getenv("SPIDERFOOT_API_KEY", "")

    async def execute(self, target: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute SpiderFoot scan via API"""
        self.status = "running"
        self.error = None

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                # Start scan
                scan_payload = {
                    "scanname": f"loom_{target}_{int(datetime.utcnow().timestamp())}",
                    "scantarget": target,
                    "modulelist": options.get("modules", "all") if options else "all",
                    "typelist": "DOMAIN_NAME,IP_ADDRESS,EMAILADDR"
                }

                response = await client.post(
                    f"{self.api_url}/api",
                    params={"func": "scanstart"},
                    data=scan_payload,
                    headers={"X-API-Key": self.api_key} if self.api_key else {}
                )

                if response.status_code != 200:
                    raise Exception(f"SpiderFoot API error: {response.status_code}")

                scan_id = response.json().get("id")

                # Poll for completion (simplified - in production, use webhooks)
                await asyncio.sleep(10)  # Give it time to run

                # Get results
                result_response = await client.get(
                    f"{self.api_url}/api",
                    params={"func": "scanresults", "id": scan_id},
                    headers={"X-API-Key": self.api_key} if self.api_key else {}
                )

                self.results = result_response.json()
                self.status = "completed"

                return {
                    "tool": self.name,
                    "target": target,
                    "status": "success",
                    "scan_id": scan_id,
                    "results": self.results,
                    "timestamp": datetime.utcnow().isoformat()
                }

        except Exception as e:
            self.status = "error"
            self.error = str(e)
            return {
                "tool": self.name,
                "target": target,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


# ============================================================================
# IntelOwl Integration (API)
# ============================================================================

class IntelOwlTool(OSINTTool):
    """IntelOwl integration via API"""

    def __init__(self):
        super().__init__("intelowl")
        self.api_url = os.getenv("INTELOWL_URL", "http://intelowl.lan")
        self.api_key = os.getenv("INTELOWL_API_KEY", "")

    async def execute(self, target: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute IntelOwl analysis via API"""
        self.status = "running"
        self.error = None

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                # Determine observable type
                observable_type = self._determine_type(target)

                # Create job
                job_payload = {
                    "observable_name": target,
                    "observable_classification": observable_type,
                    "analyzers_requested": options.get("analyzers", ["all"]) if options else ["all"]
                }

                response = await client.post(
                    f"{self.api_url}/api/jobs",
                    json=job_payload,
                    headers={"Authorization": f"Token {self.api_key}"} if self.api_key else {}
                )

                if response.status_code not in [200, 201]:
                    raise Exception(f"IntelOwl API error: {response.status_code}")

                job_id = response.json().get("job_id")

                # Poll for completion
                await asyncio.sleep(15)  # Give it time to run

                # Get results
                result_response = await client.get(
                    f"{self.api_url}/api/jobs/{job_id}",
                    headers={"Authorization": f"Token {self.api_key}"} if self.api_key else {}
                )

                self.results = result_response.json()
                self.status = "completed"

                return {
                    "tool": self.name,
                    "target": target,
                    "status": "success",
                    "job_id": job_id,
                    "results": self.results,
                    "timestamp": datetime.utcnow().isoformat()
                }

        except Exception as e:
            self.status = "error"
            self.error = str(e)
            return {
                "tool": self.name,
                "target": target,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    def _determine_type(self, target: str) -> str:
        """Determine observable type"""
        if '@' in target:
            return 'email'
        elif target.replace('.', '').isdigit():
            return 'ip'
        elif '://' in target:
            return 'url'
        else:
            return 'domain'


# ============================================================================
# SearXNG Integration (Already in main.py, but adding here for completeness)
# ============================================================================

class SearXNGTool(OSINTTool):
    """SearXNG integration"""

    def __init__(self):
        super().__init__("searxng")
        self.searxng_url = os.getenv("SEARXNG_URL", "http://192.168.50.168:8888")

    async def execute(self, target: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute SearXNG search"""
        self.status = "running"
        self.error = None

        try:
            num_results = options.get("num_results", 15) if options else 15

            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                params = {
                    "q": target,
                    "format": "json",
                    "pageno": 1
                }

                response = await client.get(
                    f"{self.searxng_url}/search",
                    params=params
                )
                response.raise_for_status()
                data = response.json()

                self.results = []
                for item in data.get("results", [])[:num_results]:
                    self.results.append({
                        "type": "search_result",
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("content", ""),
                        "engine": item.get("engine")
                    })

                self.status = "completed"

                return {
                    "tool": self.name,
                    "target": target,
                    "status": "success",
                    "results": self.results,
                    "timestamp": datetime.utcnow().isoformat()
                }

        except Exception as e:
            self.status = "error"
            self.error = str(e)
            return {
                "tool": self.name,
                "target": target,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


# ============================================================================
# Tool Registry
# ============================================================================

class ToolRegistry:
    """Registry of all available OSINT tools"""

    def __init__(self):
        self.tools = {
            "searxng": SearXNGTool(),
            "recon-ng": ReconNGTool(),
            "theharvester": TheHarvesterTool(),
            "sherlock": SherlockTool(),
            "spiderfoot": SpiderFootTool(),
            "intelowl": IntelOwlTool()
        }

    def get_tool(self, name: str) -> Optional[OSINTTool]:
        """Get tool by name"""
        return self.tools.get(name)

    def get_enabled_tools(self) -> List[OSINTTool]:
        """Get all enabled tools"""
        return [tool for tool in self.tools.values() if tool.enabled]

    def get_all_tools_status(self) -> List[Dict[str, Any]]:
        """Get status of all tools"""
        return [tool.get_status() for tool in self.tools.values()]

    async def execute_tools(self, target: str, tool_names: List[str], options: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Execute multiple tools in parallel"""
        tasks = []

        for tool_name in tool_names:
            tool = self.get_tool(tool_name)
            if tool and tool.enabled:
                tool_options = options.get(tool_name, {}) if options else {}
                tasks.append(tool.execute(target, tool_options))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error dicts
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "tool": tool_names[i],
                    "status": "error",
                    "error": str(result),
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                processed_results.append(result)

        return processed_results
