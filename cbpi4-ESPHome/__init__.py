import asyncio
import logging
from cbpi.api import *
from aioesphomeapi import APIClient, APIConnectionError

logger = logging.getLogger("cbpi4-ESPHome")


# ---------------------------------------------------------------------------
# Gedeeld verbindingsbeheer: één APIClient per host:port, hergebruikt door
# alle sensor- en actor-instances die naar dezelfde ESPHome node wijzen.
# ---------------------------------------------------------------------------

class ESPHomeConnection:
    """Eén verbinding + entity-lookup + subscriber-registratie voor één ESPHome node."""

    def __init__(self, host, port, encryption_key, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.client = APIClient(host, port, password="", noise_psk=encryption_key)
        self.connected = False
        self.entities_by_name = {}   # name / object_id -> entity key
        self.subscribers = {}        # entity key -> list of callbacks
        self._connect_task = None
        self._refcount = 0

    async def acquire(self):
        self._refcount += 1
        if self._connect_task is None or self._connect_task.done():
            self._connect_task = asyncio.create_task(self._connect_loop())

    async def release(self):
        self._refcount = max(0, self._refcount - 1)
        if self._refcount == 0:
            if self._connect_task:
                self._connect_task.cancel()
                try:
                    await self._connect_task
                except asyncio.CancelledError:
                    pass
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.connected = False
            logger.info(f"[ESPHomeConnection] Geen gebruikers meer, verbinding met {self.host} gesloten")

    async def _on_disconnect(self, expected_disconnect: bool):
        logger.warning(f"[ESPHomeConnection] Verbinding met {self.host} verbroken (expected={expected_disconnect}), reconnect volgt")
        self.connected = False

    async def _connect_loop(self):
        while True:
            if not self.connected:
                try:
                    await self.client.connect(on_stop=self._on_disconnect, login=True)
                    entities, _ = await self.client.list_entities_services()

                    self.entities_by_name = {}
                    for e in entities:
                        self.entities_by_name[e.name] = e.key
                        if getattr(e, "object_id", None):
                            self.entities_by_name[e.object_id] = e.key

                    self.client.subscribe_states(self._dispatch_state)
                    self.connected = True
                    logger.info(f"[ESPHomeConnection] Verbonden met {self.host}:{self.port}, {len(entities)} entiteiten gevonden")

                except (APIConnectionError, OSError, TimeoutError) as e:
                    if "Already connected" in str(e):
                        logger.warning(f"[ESPHomeConnection] Verbinding bleek nog actief ({self.host}), status hersteld")
                        self.connected = True
                        await asyncio.sleep(1)
                        continue
                    logger.error(f"[ESPHomeConnection] Verbindingsfout ({self.host}): {e}")
                    self.connected = False
                    await asyncio.sleep(self.timeout)
                    continue

            await asyncio.sleep(1)

    def _dispatch_state(self, state):
        key = getattr(state, "key", None)
        if key is None:
            return
        for cb in self.subscribers.get(key, []):
            try:
                cb(state)
            except Exception as e:
                logger.exception(f"[ESPHomeConnection] Fout in subscriber callback: {e}")

    def get_entity_key(self, name):
        return self.entities_by_name.get(name)

    def subscribe(self, entity_key, callback):
        self.subscribers.setdefault(entity_key, []).append(callback)

    def unsubscribe(self, entity_key, callback):
        if entity_key in self.subscribers:
            try:
                self.subscribers[entity_key].remove(callback)
            except ValueError:
                pass

    def switch_command(self, entity_key, state):
        if not self.connected:
            logger.warning(f"[ESPHomeConnection] switch_command genegeerd, niet verbonden met {self.host}")
            return
        try:
            self.client.switch_command(key=entity_key, state=state)
        except Exception as e:
            logger.exception(f"[ESPHomeConnection] switch_command error: {e}")
            self.connected = False


class ESPHomeConnectionManager:
    """Registry: max. één ESPHomeConnection per (host, port), gedeeld door alle plugin-instances."""
    _connections = {}

    @classmethod
    def get_connection(cls, host, port, encryption_key, timeout):
        conn_key = (host, port)
        conn = cls._connections.get(conn_key)
        if conn is None:
            conn = ESPHomeConnection(host, port, encryption_key, timeout)
            cls._connections[conn_key] = conn
        return conn


# ---------------------------------------------------------------------------
# Sensor
# ---------------------------------------------------------------------------

@parameters([
    Property.Select("Type", options=["CO2", "Temperature", "Relative Humidity"],
                     description="Select type of data to register for this sensor."),
    Property.Number(label="Request Timeout", configurable=True,
                     description="Reconnect-interval in seconden bij verbindingsfouten", default_value=5),
    Property.Text(label="Host", configurable=True,
                   description="IP-adres van de ESPHome node (bv. 192.168.1.50)"),
    Property.Number(label="Port", configurable=True, default_value=6053,
                     description="Native API poort van ESPHome (standaard 6053)"),
    Property.Text(label="Encryption Key", configurable=True,
                   description="API encryption key (base64) uit je ESPHome yaml. Leeg laten indien niet gebruikt."),
    Property.Text(label="Entity Name", configurable=True,
                   description="Naam (of object_id) van de sensor zoals gedefinieerd in de ESPHome yaml"),
])
class ESPHomeSensor(CBPiSensor):

    async def on_start(self):
        self.value = 0
        host = (self.props.get("Host") or "").strip()
        port = int(self.props.get("Port") or 6053)
        key = (self.props.get("Encryption Key") or "").strip() or None
        timeout = float(self.props.get("Request Timeout") or 5)
        self.entity_name = (self.props.get("Entity Name") or "").strip()

        self.conn = ESPHomeConnectionManager.get_connection(host, port, key, timeout)
        await self.conn.acquire()
        self.entity_key = None

    async def run(self):
        while self.running:
            if self.entity_key is None and self.conn.connected:
                self.entity_key = self.conn.get_entity_key(self.entity_name)
                if self.entity_key is None:
                    logger.error(f"[ESPHomeSensor] Entity '{self.entity_name}' niet gevonden op {self.conn.host}")
                else:
                    self.conn.subscribe(self.entity_key, self._on_state)
                    logger.info(f"[ESPHomeSensor] Geabonneerd op '{self.entity_name}' (key={self.entity_key})")
            await asyncio.sleep(1)

    def _on_state(self, state):
        if not hasattr(state, "state"):
            return
        try:
            self.value = round(float(state.state), 2)
            self.log_data(self.value)
            self.push_update(self.value)
        except (TypeError, ValueError):
            pass

    def get_state(self):
        return dict(value=self.value)

    async def on_stop(self):
        if self.entity_key is not None:
            self.conn.unsubscribe(self.entity_key, self._on_state)
        await self.conn.release()


# ---------------------------------------------------------------------------
# Actor
# ---------------------------------------------------------------------------

@parameters([
    Property.Text(label="Host", configurable=True,
                   description="IP-adres van de ESPHome node (bv. 192.168.1.50)"),
    Property.Number(label="Port", configurable=True, default_value=6053,
                     description="Native API poort van ESPHome (standaard 6053)"),
    Property.Text(label="Encryption Key", configurable=True,
                   description="API encryption key (base64) uit je ESPHome yaml. Leeg laten indien niet gebruikt."),
    Property.Text(label="Entity Name", configurable=True,
                   description="Naam (of object_id) van de switch-entiteit zoals gedefinieerd in de ESPHome yaml"),
    Property.Number(label="Request Timeout", configurable=True,
                     description="Reconnect-interval in seconden bij verbindingsfouten", default_value=5),
])
class ESPHomeActor(CBPiActor):

    def __init__(self, cbpi, id, props):
        super().__init__(cbpi, id, props)
        self.state = False
        self.entity_key = None

    async def on_start(self):
        host = (self.props.get("Host") or "").strip()
        port = int(self.props.get("Port") or 6053)
        key = (self.props.get("Encryption Key") or "").strip() or None
        timeout = float(self.props.get("Request Timeout") or 5)
        self.entity_name = (self.props.get("Entity Name") or "").strip()

        self.conn = ESPHomeConnectionManager.get_connection(host, port, key, timeout)
        await self.conn.acquire()
        self.entity_key = None

    async def run(self):
        while True:
            if not getattr(self, "running", False):
                await asyncio.sleep(0.5)
                continue
            if self.entity_key is None and self.conn.connected:
                self.entity_key = self.conn.get_entity_key(self.entity_name)
                if self.entity_key is None:
                    logger.error(f"[ESPHomeActor] Entity '{self.entity_name}' niet gevonden op {self.conn.host}")
                else:
                    self.conn.subscribe(self.entity_key, self._on_state)
                    logger.info(f"[ESPHomeActor] Geabonneerd op '{self.entity_name}' (key={self.entity_key})")
            await asyncio.sleep(1)

    def _on_state(self, state):
        if not hasattr(state, "state"):
            return
        new_state = bool(state.state)
        if new_state == self.state:
            return
        logger.info(f"[ESPHomeActor] Externe statuswijziging -> {new_state}")
        self.state = new_state
        try:
            asyncio.create_task(self.cbpi.actor.actor_update(self.id, 100 if new_state else 0))
        except Exception as e:
            logger.debug(f"[ESPHomeActor] actor_update failed: {e}")

    async def on(self, power=None, *args, **kwargs):
        self.state = True
        if self.entity_key is not None:
            self.conn.switch_command(self.entity_key, True)
        try:
            await self.cbpi.actor.actor_update(self.id, 100)
        except Exception:
            pass

    async def off(self, *args, **kwargs):
        self.state = False
        if self.entity_key is not None:
            self.conn.switch_command(self.entity_key, False)
        try:
            await self.cbpi.actor.actor_update(self.id, 0)
        except Exception:
            pass

    def get_state(self):
        return bool(self.state)

    async def on_stop(self):
        if self.entity_key is not None:
            self.conn.unsubscribe(self.entity_key, self._on_state)
        await self.conn.release()


def setup(cbpi):
    cbpi.plugin.register("ESPHome Sensor", ESPHomeSensor)
    cbpi.plugin.register("ESPHome Actor", ESPHomeActor)