"""
Odoo XML-RPC Client for Loom OSINT Platform

This module provides a comprehensive client for interacting with Odoo ERP/CRM
via XML-RPC. It supports both READ operations (search, read) and WRITE-GATED
operations (create, update) with explicit confirmation workflows.

Architecture:
- OdooClient: Core XML-RPC client with authentication
- OdooReadOperations: Safe read-only operations
- OdooWriteOperations: Gated write operations requiring confirmation
- OdooProposal: JSON proposal schema for write operations
"""

import os
import xmlrpc.client
import logging
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, date
from enum import Enum
import json
import uuid

logger = logging.getLogger(__name__)


class OdooOperation(str, Enum):
    """Supported Odoo write operations"""
    UPSERT_PARTNER = "upsert_partner"
    CREATE_LEAD = "create_lead"
    CREATE_PROJECT = "create_project"
    CREATE_TASKS = "create_tasks"
    SCHEDULE_ACTIVITY = "schedule_activity"
    CREATE_CALENDAR_EVENT = "create_calendar_event"
    ADD_NOTE = "add_note"


class OdooConnectionError(Exception):
    """Raised when connection to Odoo fails"""
    pass


class OdooAuthenticationError(Exception):
    """Raised when authentication fails"""
    pass


class OdooOperationError(Exception):
    """Raised when an Odoo operation fails"""
    pass


class OdooClient:
    """
    Core Odoo XML-RPC client with connection pooling and error handling.

    Supports Odoo 17+ external API via XML-RPC protocol.
    """

    def __init__(
        self,
        url: str = None,
        db: str = None,
        username: str = None,
        password: str = None
    ):
        """Initialize Odoo client with connection parameters"""
        self.url = url or os.getenv("ODOO_URL", "https://ocg.lan")
        self.db = db or os.getenv("ODOO_DB", "ocg_production")
        self.username = username or os.getenv("ODOO_USERNAME", "loom@ocg.lan")
        self.password = password or os.getenv("ODOO_PASSWORD", "")

        # Clean URL (remove trailing slash)
        self.url = self.url.rstrip('/')

        # XML-RPC endpoints
        self.common_url = f"{self.url}/xmlrpc/2/common"
        self.object_url = f"{self.url}/xmlrpc/2/object"

        # Authentication
        self._uid: Optional[int] = None
        self._common_proxy: Optional[xmlrpc.client.ServerProxy] = None
        self._models_proxy: Optional[xmlrpc.client.ServerProxy] = None

        logger.info(f"Odoo client initialized for {self.url} (DB: {self.db})")

    def _get_common_proxy(self) -> xmlrpc.client.ServerProxy:
        """Get or create common XML-RPC proxy"""
        if self._common_proxy is None:
            self._common_proxy = xmlrpc.client.ServerProxy(self.common_url)
        return self._common_proxy

    def _get_models_proxy(self) -> xmlrpc.client.ServerProxy:
        """Get or create models XML-RPC proxy"""
        if self._models_proxy is None:
            self._models_proxy = xmlrpc.client.ServerProxy(self.object_url)
        return self._models_proxy

    def authenticate(self) -> int:
        """
        Authenticate with Odoo and get user ID.

        Returns:
            int: Authenticated user ID

        Raises:
            OdooAuthenticationError: If authentication fails
        """
        if self._uid is not None:
            return self._uid

        try:
            common = self._get_common_proxy()
            self._uid = common.authenticate(
                self.db,
                self.username,
                self.password,
                {}
            )

            if not self._uid:
                raise OdooAuthenticationError(
                    f"Authentication failed for user {self.username}"
                )

            logger.info(f"Authenticated as user {self.username} (UID: {self._uid})")
            return self._uid

        except Exception as e:
            logger.error(f"Odoo authentication error: {e}")
            raise OdooAuthenticationError(f"Authentication failed: {e}")

    def get_version(self) -> Dict[str, Any]:
        """Get Odoo server version information"""
        try:
            common = self._get_common_proxy()
            version_info = common.version()
            logger.info(f"Odoo version: {version_info}")
            return version_info
        except Exception as e:
            logger.error(f"Failed to get Odoo version: {e}")
            raise OdooConnectionError(f"Connection failed: {e}")

    def execute_kw(
        self,
        model: str,
        method: str,
        args: List = None,
        kwargs: Dict = None
    ) -> Any:
        """
        Execute Odoo model method via XML-RPC.

        Args:
            model: Odoo model name (e.g., 'res.partner', 'crm.lead')
            method: Method name (e.g., 'search', 'read', 'create', 'write')
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Method execution result
        """
        uid = self.authenticate()
        models = self._get_models_proxy()

        args = args or []
        kwargs = kwargs or {}

        try:
            result = models.execute_kw(
                self.db,
                uid,
                self.password,
                model,
                method,
                args,
                kwargs
            )
            return result
        except Exception as e:
            logger.error(f"Odoo execute_kw error: {model}.{method} - {e}")
            raise OdooOperationError(f"Operation failed: {e}")

    def search(
        self,
        model: str,
        domain: List,
        offset: int = 0,
        limit: int = 100,
        order: str = None
    ) -> List[int]:
        """
        Search for records in Odoo model.

        Args:
            model: Odoo model name
            domain: Search domain (list of tuples)
            offset: Record offset
            limit: Maximum records to return
            order: Sort order

        Returns:
            List of record IDs
        """
        kwargs = {
            'offset': offset,
            'limit': limit
        }
        if order:
            kwargs['order'] = order

        return self.execute_kw(model, 'search', [domain], kwargs)

    def read(
        self,
        model: str,
        ids: List[int],
        fields: List[str] = None
    ) -> List[Dict]:
        """
        Read records from Odoo model.

        Args:
            model: Odoo model name
            ids: List of record IDs to read
            fields: List of fields to retrieve (None = all fields)

        Returns:
            List of record dictionaries
        """
        kwargs = {}
        if fields:
            kwargs['fields'] = fields

        return self.execute_kw(model, 'read', [ids], kwargs)

    def search_read(
        self,
        model: str,
        domain: List,
        fields: List[str] = None,
        offset: int = 0,
        limit: int = 100,
        order: str = None
    ) -> List[Dict]:
        """
        Combined search and read operation.

        Args:
            model: Odoo model name
            domain: Search domain
            fields: Fields to retrieve
            offset: Record offset
            limit: Maximum records
            order: Sort order

        Returns:
            List of record dictionaries
        """
        kwargs = {
            'offset': offset,
            'limit': limit
        }
        if fields:
            kwargs['fields'] = fields
        if order:
            kwargs['order'] = order

        return self.execute_kw(model, 'search_read', [domain], kwargs)

    def create(self, model: str, values: Dict) -> int:
        """
        Create a new record in Odoo.

        Args:
            model: Odoo model name
            values: Field values dictionary

        Returns:
            Created record ID
        """
        return self.execute_kw(model, 'create', [values])

    def write(self, model: str, ids: List[int], values: Dict) -> bool:
        """
        Update existing records in Odoo.

        Args:
            model: Odoo model name
            ids: List of record IDs to update
            values: Field values to update

        Returns:
            True if successful
        """
        return self.execute_kw(model, 'write', [ids, values])

    def unlink(self, model: str, ids: List[int]) -> bool:
        """
        Delete records from Odoo.

        Args:
            model: Odoo model name
            ids: List of record IDs to delete

        Returns:
            True if successful
        """
        return self.execute_kw(model, 'unlink', [ids])


class OdooReadOperations:
    """
    Safe READ-ONLY operations for Odoo entities.

    These operations can be executed without user confirmation.
    """

    def __init__(self, client: OdooClient):
        self.client = client

    def search_partners(
        self,
        query: str = None,
        email: str = None,
        phone: str = None,
        website: str = None,
        is_company: bool = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Search for partners (contacts/companies) in Odoo.

        Args:
            query: General search query (name, email, etc.)
            email: Search by email
            phone: Search by phone
            website: Search by website/domain
            is_company: Filter companies (True) or individuals (False)
            limit: Maximum results

        Returns:
            List of partner records
        """
        domain = []

        if query:
            domain.append('|')
            domain.append('|')
            domain.append(('name', 'ilike', query))
            domain.append(('email', 'ilike', query))
            domain.append(('website', 'ilike', query))

        if email:
            domain.append(('email', 'ilike', email))

        if phone:
            domain.append('|')
            domain.append(('phone', 'ilike', phone))
            domain.append(('mobile', 'ilike', phone))

        if website:
            domain.append(('website', 'ilike', website))

        if is_company is not None:
            domain.append(('is_company', '=', is_company))

        # Default to active partners only
        domain.append(('active', '=', True))

        fields = [
            'name', 'email', 'phone', 'mobile', 'website',
            'street', 'city', 'state_id', 'country_id',
            'is_company', 'company_type', 'customer_rank',
            'supplier_rank', 'comment', 'create_date', 'write_date'
        ]

        return self.client.search_read(
            'res.partner',
            domain or [('active', '=', True)],
            fields=fields,
            limit=limit,
            order='write_date desc'
        )

    def get_partner_details(self, partner_id: int) -> Dict:
        """Get full details for a specific partner"""
        results = self.client.read('res.partner', [partner_id])
        return results[0] if results else None

    def search_leads(
        self,
        partner_id: int = None,
        email: str = None,
        name: str = None,
        stage: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Search for CRM leads/opportunities.

        Args:
            partner_id: Filter by partner ID
            email: Search by email
            name: Search by opportunity name
            stage: Filter by stage
            limit: Maximum results

        Returns:
            List of lead/opportunity records
        """
        domain = []

        if partner_id:
            domain.append(('partner_id', '=', partner_id))

        if email:
            domain.append(('email_from', 'ilike', email))

        if name:
            domain.append(('name', 'ilike', name))

        if stage:
            domain.append(('stage_id.name', 'ilike', stage))

        domain.append(('active', '=', True))

        fields = [
            'name', 'partner_id', 'email_from', 'phone',
            'stage_id', 'type', 'probability', 'expected_revenue',
            'tag_ids', 'user_id', 'team_id',
            'date_deadline', 'create_date', 'write_date', 'description'
        ]

        return self.client.search_read(
            'crm.lead',
            domain or [('active', '=', True)],
            fields=fields,
            limit=limit,
            order='write_date desc'
        )

    def search_projects(
        self,
        partner_id: int = None,
        name: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """Search for projects"""
        domain = []

        if partner_id:
            domain.append(('partner_id', '=', partner_id))

        if name:
            domain.append(('name', 'ilike', name))

        domain.append(('active', '=', True))

        fields = [
            'name', 'partner_id', 'user_id', 'tag_ids',
            'task_count', 'date_start', 'date',
            'create_date', 'write_date'
        ]

        return self.client.search_read(
            'project.project',
            domain or [('active', '=', True)],
            fields=fields,
            limit=limit,
            order='write_date desc'
        )

    def search_tasks(
        self,
        project_id: int = None,
        partner_id: int = None,
        name: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """Search for project tasks"""
        domain = []

        if project_id:
            domain.append(('project_id', '=', project_id))

        if partner_id:
            domain.append(('partner_id', '=', partner_id))

        if name:
            domain.append(('name', 'ilike', name))

        domain.append(('active', '=', True))

        fields = [
            'name', 'project_id', 'partner_id', 'user_ids',
            'stage_id', 'priority', 'date_deadline',
            'create_date', 'write_date', 'description'
        ]

        return self.client.search_read(
            'project.task',
            domain or [('active', '=', True)],
            fields=fields,
            limit=limit,
            order='write_date desc'
        )

    def search_activities(
        self,
        partner_id: int = None,
        res_model: str = None,
        res_id: int = None,
        limit: int = 100
    ) -> List[Dict]:
        """Search for activities (planned actions)"""
        domain = []

        if partner_id:
            domain.append(('res_partner_id', '=', partner_id))

        if res_model:
            domain.append(('res_model', '=', res_model))

        if res_id:
            domain.append(('res_id', '=', res_id))

        domain.append(('active', '=', True))

        fields = [
            'activity_type_id', 'summary', 'date_deadline',
            'user_id', 'res_model', 'res_id', 'res_name',
            'note', 'create_date'
        ]

        return self.client.search_read(
            'mail.activity',
            domain or [('active', '=', True)],
            fields=fields,
            limit=limit,
            order='date_deadline asc'
        )

    def search_calendar_events(
        self,
        partner_ids: List[int] = None,
        name: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        limit: int = 100
    ) -> List[Dict]:
        """Search for calendar events/meetings"""
        domain = []

        if partner_ids:
            domain.append(('partner_ids', 'in', partner_ids))

        if name:
            domain.append(('name', 'ilike', name))

        if start_date:
            domain.append(('start', '>=', start_date.isoformat()))

        if end_date:
            domain.append(('stop', '<=', end_date.isoformat()))

        domain.append(('active', '=', True))

        fields = [
            'name', 'start', 'stop', 'duration',
            'partner_ids', 'user_id', 'location',
            'description', 'create_date'
        ]

        return self.client.search_read(
            'calendar.event',
            domain or [('active', '=', True)],
            fields=fields,
            limit=limit,
            order='start desc'
        )

    def get_partner_history(self, partner_id: int) -> Dict[str, Any]:
        """
        Get comprehensive history for a partner (OSINT context enrichment).

        Returns:
            Dictionary with leads, projects, tasks, activities, events
        """
        return {
            'partner': self.get_partner_details(partner_id),
            'leads': self.search_leads(partner_id=partner_id),
            'projects': self.search_projects(partner_id=partner_id),
            'tasks': self.search_tasks(partner_id=partner_id),
            'activities': self.search_activities(partner_id=partner_id),
            'calendar_events': self.search_calendar_events(partner_ids=[partner_id])
        }


class OdooWriteOperations:
    """
    WRITE-GATED operations requiring explicit user confirmation.

    All methods return OdooProposal objects that must be confirmed.
    """

    def __init__(self, client: OdooClient):
        self.client = client

    def propose_upsert_partner(
        self,
        name: str,
        email: str = None,
        phone: str = None,
        website: str = None,
        is_company: bool = True,
        street: str = None,
        city: str = None,
        country_code: str = None,
        comment: str = None,
        case_id: str = None
    ) -> 'OdooProposal':
        """Propose creating or updating a partner"""

        # Check if partner exists
        domain = []
        if email:
            domain.append(('email', '=', email))
        elif website:
            domain.append(('website', 'ilike', website))
        else:
            domain.append(('name', '=', name))

        existing = self.client.search('res.partner', domain, limit=1)

        values = {
            'name': name,
            'is_company': is_company,
            'comment': f"[Loom Case: {case_id}] {comment or 'OSINT investigation'}"
        }

        if email:
            values['email'] = email
        if phone:
            values['phone'] = phone
        if website:
            values['website'] = website
        if street:
            values['street'] = street
        if city:
            values['city'] = city
        if country_code:
            # Look up country ID
            country_ids = self.client.search(
                'res.country',
                [('code', '=', country_code.upper())],
                limit=1
            )
            if country_ids:
                values['country_id'] = country_ids[0]

        operation = {
            'op': OdooOperation.UPSERT_PARTNER,
            'payload': {
                'model': 'res.partner',
                'method': 'write' if existing else 'create',
                'ids': existing,
                'values': values
            }
        }

        summary = f"{'Update' if existing else 'Create'} partner: {name}"
        if email:
            summary += f" ({email})"

        return OdooProposal(
            summary=summary,
            operations=[operation],
            case_id=case_id
        )

    def propose_create_lead(
        self,
        name: str,
        partner_id: int = None,
        email_from: str = None,
        phone: str = None,
        description: str = None,
        expected_revenue: float = None,
        case_id: str = None
    ) -> 'OdooProposal':
        """Propose creating a CRM lead/opportunity"""

        values = {
            'name': name,
            'type': 'opportunity',
            'description': f"[Loom Case: {case_id}]\n\n{description or ''}"
        }

        if partner_id:
            values['partner_id'] = partner_id
        if email_from:
            values['email_from'] = email_from
        if phone:
            values['phone'] = phone
        if expected_revenue:
            values['expected_revenue'] = expected_revenue

        operation = {
            'op': OdooOperation.CREATE_LEAD,
            'payload': {
                'model': 'crm.lead',
                'method': 'create',
                'values': values
            }
        }

        return OdooProposal(
            summary=f"Create opportunity: {name}",
            operations=[operation],
            case_id=case_id
        )

    def propose_create_project(
        self,
        name: str,
        partner_id: int = None,
        user_id: int = None,
        date_start: date = None,
        case_id: str = None
    ) -> 'OdooProposal':
        """Propose creating a project"""

        values = {
            'name': name
        }

        if partner_id:
            values['partner_id'] = partner_id
        if user_id:
            values['user_id'] = user_id
        if date_start:
            values['date_start'] = date_start.isoformat()

        operation = {
            'op': OdooOperation.CREATE_PROJECT,
            'payload': {
                'model': 'project.project',
                'method': 'create',
                'values': values
            }
        }

        return OdooProposal(
            summary=f"Create project: {name}",
            operations=[operation],
            case_id=case_id
        )

    def propose_create_tasks(
        self,
        project_id: int,
        tasks: List[Dict[str, Any]],
        case_id: str = None
    ) -> 'OdooProposal':
        """Propose creating multiple tasks in a project"""

        operations = []
        for task in tasks:
            values = {
                'project_id': project_id,
                'name': task['name'],
                'description': f"[Loom Case: {case_id}]\n\n{task.get('description', '')}"
            }

            if 'user_ids' in task:
                values['user_ids'] = [(6, 0, task['user_ids'])]
            if 'date_deadline' in task:
                values['date_deadline'] = task['date_deadline']
            if 'priority' in task:
                values['priority'] = task['priority']

            operations.append({
                'op': OdooOperation.CREATE_TASKS,
                'payload': {
                    'model': 'project.task',
                    'method': 'create',
                    'values': values
                }
            })

        return OdooProposal(
            summary=f"Create {len(tasks)} task(s) in project",
            operations=operations,
            case_id=case_id
        )

    def propose_schedule_activity(
        self,
        res_model: str,
        res_id: int,
        activity_type: str,
        summary: str,
        date_deadline: date,
        user_id: int = None,
        note: str = None,
        case_id: str = None
    ) -> 'OdooProposal':
        """Propose scheduling an activity"""

        # Look up activity type
        activity_type_ids = self.client.search(
            'mail.activity.type',
            [('name', 'ilike', activity_type)],
            limit=1
        )

        values = {
            'res_model': res_model,
            'res_id': res_id,
            'activity_type_id': activity_type_ids[0] if activity_type_ids else 1,
            'summary': summary,
            'date_deadline': date_deadline.isoformat(),
            'note': f"[Loom Case: {case_id}]\n\n{note or ''}"
        }

        if user_id:
            values['user_id'] = user_id

        operation = {
            'op': OdooOperation.SCHEDULE_ACTIVITY,
            'payload': {
                'model': 'mail.activity',
                'method': 'create',
                'values': values
            }
        }

        return OdooProposal(
            summary=f"Schedule activity: {summary}",
            operations=[operation],
            case_id=case_id
        )

    def propose_create_calendar_event(
        self,
        name: str,
        start: datetime,
        stop: datetime,
        partner_ids: List[int] = None,
        location: str = None,
        description: str = None,
        case_id: str = None
    ) -> 'OdooProposal':
        """Propose creating a calendar event"""

        values = {
            'name': name,
            'start': start.isoformat(),
            'stop': stop.isoformat(),
            'description': f"[Loom Case: {case_id}]\n\n{description or ''}"
        }

        if partner_ids:
            values['partner_ids'] = [(6, 0, partner_ids)]
        if location:
            values['location'] = location

        operation = {
            'op': OdooOperation.CREATE_CALENDAR_EVENT,
            'payload': {
                'model': 'calendar.event',
                'method': 'create',
                'values': values
            }
        }

        return OdooProposal(
            summary=f"Create calendar event: {name}",
            operations=[operation],
            case_id=case_id
        )

    def execute_proposal(self, proposal: 'OdooProposal') -> Dict[str, Any]:
        """
        Execute a confirmed proposal.

        Args:
            proposal: OdooProposal with confirmed=True

        Returns:
            Execution results

        Raises:
            ValueError: If proposal is not confirmed
        """
        if not proposal.confirmed:
            raise ValueError("Proposal must be confirmed before execution")

        results = []

        for operation in proposal.operations:
            payload = operation['payload']
            model = payload['model']
            method = payload['method']

            try:
                if method == 'create':
                    result_id = self.client.create(model, payload['values'])
                    results.append({
                        'op': operation['op'],
                        'model': model,
                        'method': method,
                        'success': True,
                        'record_id': result_id
                    })

                elif method == 'write':
                    success = self.client.write(
                        model,
                        payload['ids'],
                        payload['values']
                    )
                    results.append({
                        'op': operation['op'],
                        'model': model,
                        'method': method,
                        'success': success,
                        'record_ids': payload['ids']
                    })

            except Exception as e:
                logger.error(f"Execution error: {e}")
                results.append({
                    'op': operation['op'],
                    'model': model,
                    'method': method,
                    'success': False,
                    'error': str(e)
                })

        return {
            'proposal_id': proposal.proposal_id,
            'case_id': proposal.case_id,
            'executed_at': datetime.now().isoformat(),
            'results': results
        }


class OdooProposal:
    """
    Represents a proposed set of Odoo write operations.

    Must be confirmed before execution.
    """

    def __init__(
        self,
        summary: str,
        operations: List[Dict],
        case_id: str = None
    ):
        self.proposal_id = str(uuid.uuid4())[:8]
        self.summary = summary
        self.operations = operations
        self.case_id = case_id
        self.requires_confirmation = True
        self.confirmed = False
        self.created_at = datetime.now().isoformat()

    def to_json(self) -> Dict[str, Any]:
        """Convert proposal to JSON format"""
        return {
            'proposal_id': self.proposal_id,
            'summary': self.summary,
            'operations': self.operations,
            'case_id': self.case_id,
            'requires_confirmation': self.requires_confirmation,
            'confirmed': self.confirmed,
            'created_at': self.created_at
        }

    def to_json_string(self) -> str:
        """Convert proposal to JSON string"""
        return json.dumps(self.to_json(), indent=2)

    def confirm(self):
        """Mark proposal as confirmed"""
        self.confirmed = True
        logger.info(f"Proposal {self.proposal_id} confirmed for execution")

    def __str__(self) -> str:
        return self.to_json_string()
