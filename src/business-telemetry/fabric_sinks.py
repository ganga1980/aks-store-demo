"""
Fabric Telemetry Sinks

Sink implementations for ingesting business telemetry data into Microsoft Fabric:
- EventHubSink: Real-time streaming via Azure Event Hubs → Fabric Real-Time Analytics
- OneLakeSink: Batch ingestion to OneLake (Delta Lake format)
- ConsoleSink: Development/debugging output
- CompositeSink: Multi-destination routing

Each sink implements the BaseSink interface for consistent event handling.
"""

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Optional dependency flags
EVENTHUB_AVAILABLE = False
ONELAKE_AVAILABLE = False
TransportType = None

try:
    from azure.eventhub.aio import EventHubProducerClient
    from azure.eventhub import EventData, TransportType
    EVENTHUB_AVAILABLE = True
except ImportError:
    logger.debug("azure-eventhub not installed. EventHubSink will be unavailable.")
    EventHubProducerClient = None
    EventData = None

try:
    from azure.storage.filedatalake.aio import DataLakeServiceClient
    ONELAKE_AVAILABLE = True
except ImportError:
    logger.debug("azure-storage-file-datalake not installed. OneLakeSink will be unavailable.")
    DataLakeServiceClient = None


class SinkType(str, Enum):
    """Available sink types."""
    EVENT_HUB = "eventhub"
    ONELAKE = "onelake"
    CONSOLE = "console"
    FILE = "file"


@dataclass
class SinkResult:
    """Result of a sink operation."""
    success: bool
    sink_type: SinkType
    events_sent: int
    error_message: Optional[str] = None
    latency_ms: Optional[float] = None


class BaseSink(ABC):
    """Abstract base class for telemetry sinks."""

    def __init__(self, sink_type: SinkType, batch_size: int = 100, flush_interval_seconds: float = 5.0):
        self.sink_type = sink_type
        self.batch_size = batch_size
        self.flush_interval = flush_interval_seconds
        self._buffer: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start the sink with background flush task."""
        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush())
        logger.info(f"{self.sink_type.value} sink started")

    async def stop(self):
        """Stop the sink and flush remaining events."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self.flush()
        logger.info(f"{self.sink_type.value} sink stopped")

    async def _periodic_flush(self):
        """Background task to periodically flush the buffer."""
        while self._running:
            await asyncio.sleep(self.flush_interval)
            if self._buffer:
                await self.flush()

    async def send(self, event: Dict[str, Any]) -> bool:
        """
        Add event to buffer and flush if batch size reached.

        Args:
            event: Event dictionary to send

        Returns:
            True if event was buffered/sent successfully
        """
        async with self._lock:
            self._buffer.append(event)

            if len(self._buffer) >= self.batch_size:
                return await self._flush_internal()
        return True

    async def send_batch(self, events: List[Dict[str, Any]]) -> SinkResult:
        """
        Send a batch of events directly.

        Args:
            events: List of event dictionaries

        Returns:
            SinkResult with operation details
        """
        start_time = datetime.now(timezone.utc)
        try:
            result = await self._send_batch_impl(events)
            latency = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            return SinkResult(
                success=True,
                sink_type=self.sink_type,
                events_sent=len(events),
                latency_ms=latency
            )
        except Exception as e:
            logger.error(f"Error sending batch to {self.sink_type.value}: {e}")
            return SinkResult(
                success=False,
                sink_type=self.sink_type,
                events_sent=0,
                error_message=str(e)
            )

    async def flush(self) -> SinkResult:
        """Flush all buffered events."""
        async with self._lock:
            return await self._flush_internal()

    async def _flush_internal(self) -> SinkResult:
        """Internal flush without lock (must be called with lock held)."""
        if not self._buffer:
            return SinkResult(success=True, sink_type=self.sink_type, events_sent=0)

        events = self._buffer.copy()
        self._buffer.clear()

        start_time = datetime.now(timezone.utc)
        try:
            await self._send_batch_impl(events)
            latency = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            logger.debug(f"Flushed {len(events)} events to {self.sink_type.value}")
            return SinkResult(
                success=True,
                sink_type=self.sink_type,
                events_sent=len(events),
                latency_ms=latency
            )
        except Exception as e:
            # Re-add events to buffer on failure
            self._buffer.extend(events)
            logger.error(f"Failed to flush to {self.sink_type.value}: {e}")
            return SinkResult(
                success=False,
                sink_type=self.sink_type,
                events_sent=0,
                error_message=str(e)
            )

    @abstractmethod
    async def _send_batch_impl(self, events: List[Dict[str, Any]]) -> None:
        """Implementation-specific batch send logic."""
        pass


class EventHubSink(BaseSink):
    """
    Azure Event Hubs sink for real-time streaming to Fabric.

    Events are sent to Event Hubs which can be connected to:
    - Fabric Real-Time Analytics (KQL Database)
    - Fabric Eventstream
    - Azure Stream Analytics

    Configuration:
        connection_string: Event Hub namespace connection string
        event_hub_name: Target Event Hub name

    Or using Managed Identity:
        fully_qualified_namespace: <namespace>.servicebus.windows.net
        event_hub_name: Target Event Hub name

    Note: Requires azure-eventhub package. If not installed, events will be
    logged as warnings and discarded.

    Transport: By default uses AMQP (port 5671). Set use_websockets=True or
    env var FABRIC_EVENT_HUB_USE_WEBSOCKETS=true to use AMQP over WebSockets
    (port 443) for environments where port 5671 is blocked.
    """

    def __init__(
        self,
        connection_string: Optional[str] = None,
        event_hub_name: Optional[str] = None,
        fully_qualified_namespace: Optional[str] = None,
        credential: Optional[Any] = None,
        batch_size: int = 100,
        flush_interval_seconds: float = 5.0,
        use_websockets: Optional[bool] = None
    ):
        super().__init__(SinkType.EVENT_HUB, batch_size, flush_interval_seconds)

        self.connection_string = connection_string
        self.event_hub_name = event_hub_name
        self.fully_qualified_namespace = fully_qualified_namespace
        self.credential = credential
        self._producer = None
        self._unavailable_logged = False

        # Determine transport type: WebSockets (port 443) or AMQP (port 5671)
        if use_websockets is None:
            use_websockets = os.getenv("FABRIC_EVENT_HUB_USE_WEBSOCKETS", "false").lower() == "true"
        self.use_websockets = use_websockets

    async def _get_producer(self):
        """Lazy initialization of Event Hub producer."""
        if not EVENTHUB_AVAILABLE:
            if not self._unavailable_logged:
                logger.warning(
                    "azure-eventhub package not installed. EventHubSink is disabled. "
                    "Install with: pip install azure-eventhub"
                )
                self._unavailable_logged = True
            return None

        if self._producer is None:
            # Determine transport type
            transport = TransportType.AmqpOverWebsocket if self.use_websockets else TransportType.Amqp
            transport_desc = "WebSockets (port 443)" if self.use_websockets else "AMQP (port 5671)"
            logger.info(f"EventHubSink using transport: {transport_desc}")

            if self.connection_string:
                self._producer = EventHubProducerClient.from_connection_string(
                    conn_str=self.connection_string,
                    eventhub_name=self.event_hub_name,
                    transport_type=transport
                )
            elif self.fully_qualified_namespace and self.credential:
                self._producer = EventHubProducerClient(
                    fully_qualified_namespace=self.fully_qualified_namespace,
                    eventhub_name=self.event_hub_name,
                    credential=self.credential,
                    transport_type=transport
                )
            else:
                raise ValueError(
                    "Either connection_string or (fully_qualified_namespace + credential) required"
                )
        return self._producer

    async def _send_batch_impl(self, events: List[Dict[str, Any]]) -> None:
        """Send events to Event Hub."""
        producer = await self._get_producer()

        if producer is None:
            # Event Hub not available, skip silently (already logged warning)
            logger.debug(f"Skipping {len(events)} events - EventHub not available")
            return

        try:
            event_batch = await producer.create_batch()

            for event in events:
                event_data = EventData(json.dumps(event, default=str))

                # Add properties for routing/filtering in Fabric
                if "event_type" in event:
                    event_data.properties["event_type"] = event["event_type"]
                if "event_source" in event:
                    event_data.properties["event_source"] = event["event_source"]

                try:
                    event_batch.add(event_data)
                except ValueError:
                    # Batch is full, send and create new
                    await producer.send_batch(event_batch)
                    event_batch = await producer.create_batch()
                    event_batch.add(event_data)

            if len(event_batch) > 0:
                await producer.send_batch(event_batch)

            logger.info(f"Sent {len(events)} events to Event Hub")
        except Exception as e:
            # Reset producer on connection failure so it can be recreated
            logger.warning(f"Event Hub send failed, resetting producer: {e}")
            self._producer = None
            raise

    async def stop(self):
        """Stop and close the producer."""
        await super().stop()
        if self._producer:
            try:
                await self._producer.close()
            except Exception as e:
                # Connection may already be closed or in an error state
                logger.debug(f"Error closing Event Hub producer (may be expected): {e}")
            finally:
                self._producer = None


class OneLakeSink(BaseSink):
    """
    OneLake sink for batch ingestion to Fabric Lakehouse.

    Events are written as Delta Lake parquet files to OneLake,
    which can be queried via:
    - Fabric Lakehouse SQL endpoint
    - Fabric Spark notebooks
    - Power BI DirectLake

    File naming convention:
        {workspace}/{lakehouse}/Files/business_telemetry/{event_type}/
            year={YYYY}/month={MM}/day={DD}/
            {timestamp}_{batch_id}.parquet

    Configuration:
        account_name: OneLake storage account
        workspace_id: Fabric workspace GUID
        lakehouse_id: Lakehouse GUID

    Note: Requires azure-storage-file-datalake package. If not installed, events
    will be logged as warnings and discarded.
    """

    def __init__(
        self,
        account_name: str = "onelake",
        workspace_id: Optional[str] = None,
        lakehouse_id: Optional[str] = None,
        credential: Optional[Any] = None,
        base_path: str = "Files/business_telemetry",
        batch_size: int = 1000,
        flush_interval_seconds: float = 60.0,
        output_format: str = "jsonl"  # jsonl or parquet
    ):
        super().__init__(SinkType.ONELAKE, batch_size, flush_interval_seconds)

        self.account_name = account_name
        self.workspace_id = workspace_id
        self.lakehouse_id = lakehouse_id
        self.credential = credential
        self.base_path = base_path
        self.output_format = output_format
        self._client = None
        self._unavailable_logged = False

    async def _get_client(self):
        """Lazy initialization of DataLake client."""
        if not ONELAKE_AVAILABLE:
            if not self._unavailable_logged:
                logger.warning(
                    "azure-storage-file-datalake package not installed. OneLakeSink is disabled. "
                    "Install with: pip install azure-storage-file-datalake"
                )
                self._unavailable_logged = True
            return None

        if self._client is None:
            account_url = f"https://{self.account_name}.dfs.fabric.microsoft.com"

            if self.credential:
                self._client = DataLakeServiceClient(
                    account_url=account_url,
                    credential=self.credential
                )
            else:
                from azure.identity.aio import DefaultAzureCredential
                self._client = DataLakeServiceClient(
                    account_url=account_url,
                    credential=DefaultAzureCredential()
                )
        return self._client

    def _get_partition_path(self, event_type: str) -> str:
        """Generate partitioned path based on event type and current time."""
        now = datetime.now(timezone.utc)
        return (
            f"{self.base_path}/{event_type}/"
            f"year={now.year}/month={now.month:02d}/day={now.day:02d}"
        )

    def _get_filename(self) -> str:
        """Generate unique filename for batch."""
        import uuid
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        batch_id = str(uuid.uuid4())[:8]
        return f"{timestamp}_{batch_id}.{self.output_format}"

    async def _send_batch_impl(self, events: List[Dict[str, Any]]) -> None:
        """Write events to OneLake as partitioned files."""
        client = await self._get_client()

        # Skip if OneLake is not available
        if client is None:
            logger.debug(f"OneLakeSink: Skipping {len(events)} events (azure-storage-file-datalake not installed)")
            return

        # Group events by type for partitioned storage
        events_by_type: Dict[str, List[Dict]] = {}
        for event in events:
            event_type = event.get("event_type", "unknown").replace(".", "_")
            if event_type not in events_by_type:
                events_by_type[event_type] = []
            events_by_type[event_type].append(event)

        # Container path: {workspace_id}/{lakehouse_id}
        container_name = f"{self.workspace_id}/{self.lakehouse_id}" if self.workspace_id else "default"

        async with client:
            file_system_client = client.get_file_system_client(container_name)

            for event_type, type_events in events_by_type.items():
                partition_path = self._get_partition_path(event_type)
                filename = self._get_filename()
                file_path = f"{partition_path}/{filename}"

                # Ensure directory exists
                directory_client = file_system_client.get_directory_client(partition_path)
                try:
                    await directory_client.create_directory()
                except Exception:
                    pass  # Directory may already exist

                # Write events
                file_client = file_system_client.get_file_client(file_path)

                if self.output_format == "jsonl":
                    content = "\n".join(json.dumps(e, default=str) for e in type_events)
                    await file_client.upload_data(content.encode("utf-8"), overwrite=True)
                else:
                    # For parquet, use pyarrow if available
                    try:
                        import pyarrow as pa
                        import pyarrow.parquet as pq
                        import io

                        table = pa.Table.from_pylist(type_events)
                        buffer = io.BytesIO()
                        pq.write_table(table, buffer)
                        buffer.seek(0)
                        await file_client.upload_data(buffer.read(), overwrite=True)
                    except ImportError:
                        # Fallback to JSONL
                        content = "\n".join(json.dumps(e, default=str) for e in type_events)
                        await file_client.upload_data(content.encode("utf-8"), overwrite=True)

                logger.info(f"Wrote {len(type_events)} events to OneLake: {file_path}")

    async def stop(self):
        """Stop and close the client."""
        await super().stop()
        if self._client:
            await self._client.close()


class ConsoleSink(BaseSink):
    """
    Console sink for development and debugging.

    Outputs events to stdout in a human-readable format.
    """

    def __init__(
        self,
        pretty_print: bool = True,
        batch_size: int = 1,
        flush_interval_seconds: float = 0.1
    ):
        super().__init__(SinkType.CONSOLE, batch_size, flush_interval_seconds)
        self.pretty_print = pretty_print

    async def _send_batch_impl(self, events: List[Dict[str, Any]]) -> None:
        """Print events to console."""
        for event in events:
            if self.pretty_print:
                print(f"\n{'='*60}")
                print(f"📊 Business Event: {event.get('event_type', 'unknown')}")
                print(f"   Source: {event.get('event_source', 'unknown')}")
                print(f"   Time: {event.get('event_time', 'unknown')}")
                print(f"   ID: {event.get('event_id', 'unknown')}")
                print(f"{'='*60}")
                print(json.dumps(event, indent=2, default=str))
            else:
                print(json.dumps(event, default=str))


class FileSink(BaseSink):
    """
    File sink for local storage and testing.

    Writes events to local files, useful for:
    - Local development
    - Testing event generation
    - Offline analysis
    """

    def __init__(
        self,
        output_dir: str = "./business_telemetry_output",
        partition_by_type: bool = True,
        partition_by_date: bool = True,
        batch_size: int = 100,
        flush_interval_seconds: float = 10.0
    ):
        super().__init__(SinkType.FILE, batch_size, flush_interval_seconds)
        self.output_dir = Path(output_dir)
        self.partition_by_type = partition_by_type
        self.partition_by_date = partition_by_date

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_output_path(self, event_type: str) -> Path:
        """Generate output path based on partitioning settings."""
        path = self.output_dir

        if self.partition_by_type:
            path = path / event_type.replace(".", "_")

        if self.partition_by_date:
            now = datetime.now(timezone.utc)
            path = path / f"{now.year}" / f"{now.month:02d}" / f"{now.day:02d}"

        path.mkdir(parents=True, exist_ok=True)
        return path

    async def _send_batch_impl(self, events: List[Dict[str, Any]]) -> None:
        """Write events to local files."""
        import uuid

        # Group events by type
        events_by_type: Dict[str, List[Dict]] = {}
        for event in events:
            event_type = event.get("event_type", "unknown")
            if event_type not in events_by_type:
                events_by_type[event_type] = []
            events_by_type[event_type].append(event)

        for event_type, type_events in events_by_type.items():
            output_path = self._get_output_path(event_type)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            batch_id = str(uuid.uuid4())[:8]
            filename = f"{timestamp}_{batch_id}.jsonl"

            file_path = output_path / filename

            with open(file_path, "w") as f:
                for event in type_events:
                    f.write(json.dumps(event, default=str) + "\n")

            logger.info(f"Wrote {len(type_events)} events to {file_path}")


class CompositeSink(BaseSink):
    """
    Composite sink that routes events to multiple destinations.

    Useful for:
    - Sending to both Event Hub (real-time) and OneLake (batch)
    - Adding console output for debugging alongside production sinks
    - Gradual migration between sink types
    """

    def __init__(
        self,
        sinks: List[BaseSink],
        fail_fast: bool = False
    ):
        # Use minimal buffering since child sinks handle their own
        super().__init__(SinkType.CONSOLE, batch_size=1, flush_interval_seconds=0.1)
        self.sinks = sinks
        self.fail_fast = fail_fast

    async def start(self):
        """Start all child sinks."""
        for sink in self.sinks:
            await sink.start()
        await super().start()

    async def stop(self):
        """Stop all child sinks."""
        await super().stop()
        for sink in self.sinks:
            await sink.stop()

    async def _send_batch_impl(self, events: List[Dict[str, Any]]) -> None:
        """Send events to all child sinks."""
        results: List[SinkResult] = []

        for sink in self.sinks:
            try:
                result = await sink.send_batch(events)
                results.append(result)

                if not result.success and self.fail_fast:
                    raise Exception(f"Sink {sink.sink_type.value} failed: {result.error_message}")
            except Exception as e:
                logger.error(f"Error in composite sink ({sink.sink_type.value}): {e}")
                if self.fail_fast:
                    raise

        # Log summary
        successful = sum(1 for r in results if r.success)
        logger.debug(f"Composite sink: {successful}/{len(self.sinks)} sinks succeeded")


def create_sink_from_config(config: Dict[str, Any]) -> BaseSink:
    """
    Factory function to create a sink from configuration dictionary.

    Args:
        config: Dictionary with 'type' and type-specific settings

    Returns:
        Configured sink instance
    """
    sink_type = config.get("type", "console").lower()

    if sink_type == "eventhub":
        return EventHubSink(
            connection_string=config.get("connection_string"),
            event_hub_name=config.get("event_hub_name"),
            fully_qualified_namespace=config.get("fully_qualified_namespace"),
            batch_size=config.get("batch_size", 100),
            flush_interval_seconds=config.get("flush_interval", 5.0)
        )

    elif sink_type == "onelake":
        return OneLakeSink(
            account_name=config.get("account_name", "onelake"),
            workspace_id=config.get("workspace_id"),
            lakehouse_id=config.get("lakehouse_id"),
            base_path=config.get("base_path", "Files/business_telemetry"),
            batch_size=config.get("batch_size", 1000),
            flush_interval_seconds=config.get("flush_interval", 60.0),
            output_format=config.get("output_format", "jsonl")
        )

    elif sink_type == "file":
        return FileSink(
            output_dir=config.get("output_dir", "./business_telemetry_output"),
            partition_by_type=config.get("partition_by_type", True),
            partition_by_date=config.get("partition_by_date", True),
            batch_size=config.get("batch_size", 100),
            flush_interval_seconds=config.get("flush_interval", 10.0)
        )

    elif sink_type == "console":
        return ConsoleSink(
            pretty_print=config.get("pretty_print", True),
            batch_size=config.get("batch_size", 1),
            flush_interval_seconds=config.get("flush_interval", 0.1)
        )

    else:
        raise ValueError(f"Unknown sink type: {sink_type}")
