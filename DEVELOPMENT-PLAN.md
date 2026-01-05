# Loom Development Plan: Node-Based Intelligence Platform

## Executive Summary

This plan outlines the transformation of Loom from an OSINT orchestration platform into a **self-contained, node-based intelligence platform** that runs on Raspberry Pi 5. The system will be managed via SSH and follow strict architectural principles for composability, observability, and reversibility.

---

## Part 1: SSH-Based Development Workflow

### 1.1 Development Environment Setup

#### Local Development Machine (Mac)
- **Primary IDE**: Cursor with AI agent
- **SSH Access**: Configured to Pi-Forge (192.168.50.157)
- **Git Workflow**: Local commits, push to remote, pull on Pi-Forge

#### Remote Development Target (Pi-Forge)
- **Host**: 192.168.50.157
- **User**: admin
- **SSH Key**: `keys/id_ed25519_piforge`
- **Working Directory**: `/home/admin/loom` or `/opt/loom`

### 1.2 SSH Development Workflow

#### Initial Setup
```bash
# On local machine (Mac)
cd /Users/origin/GitHub/Loom

# Test SSH connection
ssh -i keys/id_ed25519_piforge admin@192.168.50.157 "echo 'Connection successful'"

# Setup remote development directory
ssh -i keys/id_ed25519_piforge admin@192.168.50.157 << 'EOF'
mkdir -p ~/loom-dev
cd ~/loom-dev
git clone <repository-url> . || echo "Directory exists"
EOF
```

#### Daily Development Workflow
```bash
# 1. Make changes locally in Cursor
# 2. Commit changes
git add .
git commit -m "feat: add new node type"

# 3. Push to remote
git push origin main

# 4. SSH to Pi-Forge and pull
ssh -i keys/id_ed25519_piforge admin@192.168.50.157 << 'EOF'
cd ~/loom-dev
git pull origin main
docker compose down
docker compose up -d --build
docker compose logs -f loom-api
EOF
```

### 1.3 Automated Development Scripts

#### `dev-sync.sh` - Sync code to Pi-Forge
```bash
#!/bin/bash
# Syncs local changes to Pi-Forge and restarts services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY_FILE="$SCRIPT_DIR/keys/id_ed25519_piforge"
REMOTE_HOST="admin@192.168.50.157"
REMOTE_DIR="~/loom-dev"

echo "🔄 Syncing to Pi-Forge..."

# Push to git first (if not already pushed)
git push origin main || echo "⚠️  Git push failed or already up to date"

# SSH and pull on remote
ssh -i "$KEY_FILE" "$REMOTE_HOST" << EOF
cd $REMOTE_DIR
git pull origin main || echo "⚠️  Git pull failed"
echo "✅ Code synced"
EOF

echo "✅ Sync complete"
```

#### `dev-deploy.sh` - Deploy and restart
```bash
#!/bin/bash
# Deploys changes and restarts Docker containers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY_FILE="$SCRIPT_DIR/keys/id_ed25519_piforge"
REMOTE_HOST="admin@192.168.50.157"
REMOTE_DIR="~/loom-dev"

echo "🚀 Deploying to Pi-Forge..."

ssh -i "$KEY_FILE" "$REMOTE_HOST" << EOF
cd $REMOTE_DIR
docker compose down
docker compose build --no-cache
docker compose up -d
echo "✅ Deployment complete"
docker compose ps
EOF

echo "✅ Deployment finished"
```

#### `dev-logs.sh` - Stream logs
```bash
#!/bin/bash
# Stream logs from Pi-Forge

KEY_FILE="keys/id_ed25519_piforge"
REMOTE_HOST="admin@192.168.50.157"
REMOTE_DIR="~/loom-dev"

ssh -i "$KEY_FILE" "$REMOTE_HOST" "cd $REMOTE_DIR && docker compose logs -f loom-api"
```

#### `dev-shell.sh` - Interactive shell on Pi-Forge
```bash
#!/bin/bash
# Open interactive shell on Pi-Forge

KEY_FILE="keys/id_ed25519_piforge"
REMOTE_HOST="admin@192.168.50.157"
REMOTE_DIR="~/loom-dev"

ssh -i "$KEY_FILE" -t "$REMOTE_HOST" "cd $REMOTE_DIR && exec \$SHELL"
```

### 1.4 Cursor AI Agent Configuration

#### `.cursorrules` - AI Agent Guidelines
```markdown
# Loom Development Rules

## Architecture Principles
1. **Node-Based**: Every feature is a node with defined inputs/outputs
2. **Event-Driven**: All coordination via structured events
3. **Adjacency, Not Control**: Observe host filesystem, don't replace it
4. **Read-Only Default**: Suggestions before mutations
5. **Local-First**: Fully functional without external services

## Code Style
- Python 3.11+ with type hints
- Async/await for all I/O operations
- Pydantic models for data validation
- Structured logging with JSON format
- Docker-first development

## Testing
- Unit tests for each node
- Integration tests for event flows
- Docker compose for local testing
- SSH-based deployment to Pi-Forge

## SSH Workflow
- Always test locally first
- Use dev-sync.sh to push changes
- Use dev-deploy.sh to deploy
- Monitor with dev-logs.sh
```

### 1.5 Remote Development with VS Code/Cursor Remote SSH

#### Setup Remote SSH Extension
1. Install "Remote - SSH" extension in Cursor
2. Configure SSH config:
```ssh-config
Host pi-forge
    HostName 192.168.50.157
    User admin
    IdentityFile ~/GitHub/Loom/keys/id_ed25519_piforge
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

3. Connect: `Cmd+Shift+P` → "Remote-SSH: Connect to Host" → `pi-forge`
4. Open folder: `/home/admin/loom-dev`

This allows direct editing on Pi-Forge with full Cursor AI support.

---

## Part 2: Architecture Transformation Plan

### 2.1 Current State Analysis

**Current Architecture:**
- Monolithic FastAPI application
- Direct tool integrations (SearXNG, Recon-ng, etc.)
- Synchronous orchestration
- File-based + database storage

**Target Architecture:**
- Node-based system with event bus
- Independent, composable nodes
- Asynchronous event-driven coordination
- Single data volume for portability

### 2.2 Node Architecture Design

#### Node Contract
```python
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from pydantic import BaseModel
from enum import Enum

class NodeType(str, Enum):
    SENSE = "sense"      # Observes system/network
    MEMORY = "memory"    # Stores/retrieves data
    REASON = "reason"    # AI/LLM processing
    ACT = "act"         # Performs actions (with permission)

class Event(BaseModel):
    """Structured event for node communication"""
    event_id: str
    event_type: str
    source_node: str
    timestamp: datetime
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = {}

class NodeContract(BaseModel):
    """Node definition and contract"""
    node_id: str
    node_type: NodeType
    name: str
    description: str
    version: str
    
    # Input/Output contracts
    input_schema: Dict[str, Any]  # JSON Schema
    output_schema: Dict[str, Any]  # JSON Schema
    
    # Permissions
    read_paths: List[str] = []      # Filesystem paths node can read
    write_paths: List[str] = []      # Filesystem paths node can write
    network_access: bool = False    # Can make network requests
    docker_access: bool = False      # Can access Docker
    
    # Behavior
    default_mode: str = "observe"   # "observe" or "suggest" or "act"
    reversible: bool = True          # Actions can be undone

class Node(ABC):
    """Base class for all Loom nodes"""
    
    def __init__(self, contract: NodeContract):
        self.contract = contract
        self.status = "idle"
        self.last_event: Optional[Event] = None
    
    @abstractmethod
    async def process(self, event: Event) -> List[Event]:
        """Process incoming event and emit output events"""
        pass
    
    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Return node health status"""
        pass
```

### 2.3 Event Bus Architecture

#### Event Bus Implementation
```python
from typing import Callable, List
import asyncio
from collections import defaultdict

class EventBus:
    """Central event bus for node communication"""
    
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.event_history: List[Event] = []
        self.max_history = 10000
    
    async def publish(self, event: Event):
        """Publish event to all subscribers"""
        # Store in history
        self.event_history.append(event)
        if len(self.event_history) > self.max_history:
            self.event_history.pop(0)
        
        # Notify subscribers
        handlers = self.subscribers.get(event.event_type, [])
        handlers.extend(self.subscribers.get("*", []))  # Wildcard subscribers
        
        await asyncio.gather(*[handler(event) for handler in handlers])
    
    def subscribe(self, event_type: str, handler: Callable):
        """Subscribe to event type"""
        self.subscribers[event_type].append(handler)
    
    def get_history(self, event_type: Optional[str] = None) -> List[Event]:
        """Get event history, optionally filtered by type"""
        if event_type:
            return [e for e in self.event_history if e.event_type == event_type]
        return self.event_history
```

### 2.4 Node Examples

#### Sense Node: Filesystem Observer
```python
class FilesystemObserverNode(Node):
    """Observes filesystem changes without modifying"""
    
    def __init__(self):
        contract = NodeContract(
            node_id="fs-observer-001",
            node_type=NodeType.SENSE,
            name="Filesystem Observer",
            description="Monitors filesystem changes in specified paths",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "watch_paths": {"type": "array", "items": {"type": "string"}},
                    "event_types": {"type": "array", "items": {"type": "string"}}
                }
            },
            output_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "change_type": {"type": "string"},
                    "metadata": {"type": "object"}
                }
            },
            read_paths=["/data", "/home/admin"],
            default_mode="observe"
        )
        super().__init__(contract)
    
    async def process(self, event: Event) -> List[Event]:
        """Process filesystem observation request"""
        # Implementation: Watch filesystem, emit change events
        # Never modifies filesystem
        pass
```

#### Memory Node: Case Storage
```python
class CaseStorageNode(Node):
    """Stores and retrieves case data"""
    
    def __init__(self, data_dir: Path):
        contract = NodeContract(
            node_id="case-storage-001",
            node_type=NodeType.MEMORY,
            name="Case Storage",
            description="Persistent storage for investigation cases",
            version="1.0.0",
            write_paths=[str(data_dir)],
            default_mode="act",  # Storage is an action
            reversible=True  # Can delete/restore cases
        )
        super().__init__(contract)
        self.data_dir = data_dir
    
    async def process(self, event: Event) -> List[Event]:
        """Store or retrieve case data"""
        # Implementation: Read/write to data volume
        pass
```

#### Reason Node: Ollama Integration
```python
class OllamaReasonNode(Node):
    """AI reasoning via Ollama"""
    
    def __init__(self, ollama_url: str, model: str):
        contract = NodeContract(
            node_id="ollama-reason-001",
            node_type=NodeType.REASON,
            name="Ollama Reasoner",
            description="AI-powered reasoning and synthesis",
            version="1.0.0",
            network_access=True,  # Needs network for Ollama API
            default_mode="observe"  # Only reasons, doesn't act
        )
        super().__init__(contract)
        self.ollama_url = ollama_url
        self.model = model
    
    async def process(self, event: Event) -> List[Event]:
        """Process reasoning request"""
        # Implementation: Call Ollama API, emit reasoning results
        pass
```

#### Act Node: OSINT Tool Execution
```python
class OSINTToolNode(Node):
    """Executes OSINT tools (with permission)"""
    
    def __init__(self, tool_name: str, tool_config: Dict):
        contract = NodeContract(
            node_id=f"osint-{tool_name}-001",
            node_type=NodeType.ACT,
            name=f"OSINT Tool: {tool_name}",
            description=f"Executes {tool_name} OSINT tool",
            version="1.0.0",
            docker_access=True,  # May need Docker
            network_access=True,  # May need network
            default_mode="suggest",  # Suggest before executing
            reversible=False  # Tool execution can't be undone
        )
        super().__init__(contract)
        self.tool_name = tool_name
        self.tool_config = tool_config
    
    async def process(self, event: Event) -> List[Event]:
        """Execute OSINT tool (after permission check)"""
        # Implementation: Check permissions, execute tool, emit results
        pass
```

### 2.5 Migration Strategy

#### Phase 1: Foundation (Weeks 1-2)
1. Implement Event Bus
2. Create Node base classes and contracts
3. Build node registry
4. Create development tooling

#### Phase 2: Node Extraction (Weeks 3-4)
1. Extract OSINT tools into Act nodes
2. Extract storage into Memory nodes
3. Extract Ollama into Reason node
4. Create Sense nodes for system observation

#### Phase 3: Event Integration (Weeks 5-6)
1. Replace direct calls with event publishing
2. Implement event routing
3. Add event history and audit logging
4. Test node composition

#### Phase 4: Permission System (Weeks 7-8)
1. Implement permission checking
2. Add "suggest" mode for Act nodes
3. Create action approval workflow
4. Add reversibility tracking

#### Phase 5: Portability (Weeks 9-10)
1. Consolidate data into single volume
2. Create backup/restore system
3. Test full system restore
4. Document deployment process

---

## Part 3: Docker Architecture

### 3.1 Container Structure

```
loom/
├── docker-compose.yml
├── .env
├── data/                    # Single data volume (portable)
│   ├── cases/
│   ├── events/
│   ├── nodes/
│   └── config/
├── nodes/                   # Node implementations
│   ├── sense/
│   ├── memory/
│   ├── reason/
│   └── act/
├── core/                    # Core system
│   ├── event_bus.py
│   ├── node_registry.py
│   └── permission_manager.py
└── api/                     # API layer
    └── main.py
```

### 3.2 Docker Compose Structure

```yaml
services:
  loom-event-bus:
    image: python:3.11-slim
    container_name: loom-event-bus
    volumes:
      - ./core:/app/core
      - ./data:/data
    command: python -m core.event_bus
    restart: unless-stopped

  loom-api:
    image: python:3.11-slim
    container_name: loom-api
    volumes:
      - ./api:/app/api
      - ./core:/app/core
      - ./nodes:/app/nodes
      - ./data:/data
      - ./keys:/app/keys:ro
    ports:
      - "8787:8787"
    command: uvicorn api.main:app --host 0.0.0.0 --port 8787
    depends_on:
      - loom-event-bus
    restart: unless-stopped

  loom-nodes:
    image: python:3.11-slim
    container_name: loom-nodes
    volumes:
      - ./nodes:/app/nodes
      - ./core:/app/core
      - ./data:/data
      - /var/run/docker.sock:/var/run/docker.sock:ro
    command: python -m nodes.node_runner
    depends_on:
      - loom-event-bus
    restart: unless-stopped

  loom-ui:
    image: nginx:alpine
    container_name: loom-ui
    volumes:
      - ./ui:/usr/share/nginx/html:ro
    ports:
      - "8788:80"
    restart: unless-stopped
```

### 3.3 Data Volume Structure

```
/data/
├── cases/              # Investigation cases
│   └── <case_id>/
├── events/             # Event history
│   └── events.db
├── nodes/              # Node state
│   └── <node_id>/
├── config/             # Configuration
│   └── nodes.json
└── backups/            # Automated backups
    └── <timestamp>/
```

### 3.4 Portability Strategy

#### Backup Script
```bash
#!/bin/bash
# Backup entire Loom state

BACKUP_DIR="/data/backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Copy data volume
tar -czf "$BACKUP_DIR/loom-data.tar.gz" /data/* --exclude=/data/backups

# Export Docker images
docker save loom-api loom-event-bus loom-nodes | gzip > "$BACKUP_DIR/images.tar.gz"

# Export configuration
cp docker-compose.yml .env "$BACKUP_DIR/"

echo "✅ Backup created: $BACKUP_DIR"
```

#### Restore Script
```bash
#!/bin/bash
# Restore Loom from backup

BACKUP_DIR="$1"

# Restore data
tar -xzf "$BACKUP_DIR/loom-data.tar.gz" -C /

# Load Docker images
gunzip -c "$BACKUP_DIR/images.tar.gz" | docker load

# Restore configuration
cp "$BACKUP_DIR/docker-compose.yml" .
cp "$BACKUP_DIR/.env" .

# Start services
docker compose up -d

echo "✅ Restore complete"
```

---

## Part 4: Development Roadmap

### 4.1 Immediate Actions (Week 1)

1. **Setup SSH Development Environment**
   - [ ] Test SSH connection to Pi-Forge
   - [ ] Create development scripts (dev-sync.sh, dev-deploy.sh, etc.)
   - [ ] Configure Cursor Remote SSH
   - [ ] Setup git workflow

2. **Create Architecture Foundation**
   - [ ] Design Event Bus
   - [ ] Create Node base classes
   - [ ] Implement Node Contract system
   - [ ] Create Node Registry

3. **Documentation**
   - [ ] Document node architecture
   - [ ] Create node development guide
   - [ ] Document event schema

### 4.2 Short Term (Weeks 2-4)

1. **Implement Core Systems**
   - [ ] Event Bus with persistence
   - [ ] Node Registry
   - [ ] Permission Manager
   - [ ] Event History/Audit

2. **Create First Nodes**
   - [ ] Filesystem Observer (Sense)
   - [ ] Case Storage (Memory)
   - [ ] Ollama Reasoner (Reason)
   - [ ] SearXNG Tool (Act)

3. **Testing Infrastructure**
   - [ ] Unit test framework
   - [ ] Integration test suite
   - [ ] Node testing utilities

### 4.3 Medium Term (Weeks 5-8)

1. **Migrate Existing Tools**
   - [ ] Convert all OSINT tools to Act nodes
   - [ ] Migrate storage to Memory nodes
   - [ ] Convert orchestration to event-driven

2. **Permission System**
   - [ ] Implement permission checking
   - [ ] Add "suggest" mode
   - [ ] Create approval workflow
   - [ ] Add reversibility tracking

3. **UI Updates**
   - [ ] Node visualization
   - [ ] Event flow diagram
   - [ ] Permission management UI

### 4.4 Long Term (Weeks 9-12)

1. **Portability**
   - [ ] Single data volume consolidation
   - [ ] Backup/restore system
   - [ ] Migration tools

2. **Advanced Features**
   - [ ] Node composition UI
   - [ ] Custom node development
   - [ ] Node marketplace
   - [ ] Performance optimization

3. **Production Readiness**
   - [ ] Security hardening
   - [ ] Performance testing
   - [ ] Documentation completion
   - [ ] Deployment automation

---

## Part 5: Success Metrics

### Technical Metrics
- ✅ All functionality implemented as nodes
- ✅ Zero direct coupling between nodes
- ✅ 100% event-driven communication
- ✅ Single data volume for full portability
- ✅ All actions logged and reversible
- ✅ Runs on Raspberry Pi 5 (low-power)

### Development Metrics
- ✅ SSH-based workflow functional
- ✅ Automated deployment working
- ✅ Remote development with Cursor
- ✅ Test coverage > 80%
- ✅ Documentation complete

### Operational Metrics
- ✅ System restore from backup < 5 minutes
- ✅ Node addition without system restart
- ✅ Event history queryable
- ✅ Permission system enforced

---

## Part 6: Risk Mitigation

### Technical Risks
1. **Event Bus Performance**: Use async/await, consider Redis for scale
2. **Node Isolation**: Docker containers per node type
3. **Data Volume Size**: Implement data retention policies
4. **Pi 5 Constraints**: Optimize for low memory, efficient I/O

### Development Risks
1. **SSH Connectivity**: Local fallback development environment
2. **Remote Debugging**: VS Code Remote debugging setup
3. **Code Sync Issues**: Git-based workflow with conflict resolution

### Operational Risks
1. **Data Loss**: Automated backups, redundant storage
2. **Node Failures**: Health checks, automatic restart
3. **Permission Bypass**: Strict permission enforcement, audit logs

---

## Conclusion

This plan provides a comprehensive roadmap for transforming Loom into a node-based intelligence platform while maintaining a smooth SSH-based development workflow. The architecture emphasizes composability, observability, and portability while respecting the host system and operating reliably on low-power hardware.

Next Steps:
1. Review and approve plan
2. Setup SSH development environment
3. Begin Phase 1 implementation
4. Iterate based on learnings

