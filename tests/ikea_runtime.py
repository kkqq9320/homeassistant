"""실제 HA 자동화에 합성 MQTT와 조명 서비스 경계를 연결한다."""

import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import platform
import shutil
import tempfile
import time
from typing import Any
import unittest
from unittest.mock import patch

import yaml
from homeassistant import bootstrap, config_entries, core, loader
from homeassistant.components import automation
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.const import __version__
from homeassistant.setup import async_setup_component

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "blueprints/automation/z2m_ikea_e1744_light_control.yaml"
BLUEPRINT_RELATIVE = "local/z2m_ikea_e1744_light_control.yaml"
ENTITY = "light.ikea_test"
print(f"Runtime: HA {__version__}; Python {platform.python_version()}", flush=True)


@dataclass(frozen=True)
class RecordedCall:
    data: dict[str, Any]
    at: float
    context_id: str


class IkeaBlueprintCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ikea-ha-")
        self.addCleanup(self.temporary.cleanup)
        self.config_dir = Path(self.temporary.name)
        self.hass = core.HomeAssistant(self.temporary.name)
        loader.async_setup(self.hass)
        self.hass.config.time_zone = "UTC"
        self.hass.loop.slow_callback_duration = 1.0
        self.light_calls = []
        self.click_calls = []
        self.subscribed_topics = []
        self.subscriptions = {}
        self.service_gate = None
        self.service_error = None
        self._call_event = asyncio.Event()
        self._click_event = asyncio.Event()
        self.hass.services.async_register("light", "turn_on", self._record_light)
        self.hass.services.async_register("test", "record_click", self._record_click)
        self.transport_patch = patch(
            "homeassistant.components.mqtt.trigger.async_subscribe_internal", self._subscribe
        )
        self.transport_patch.start()
        self.addCleanup(self.transport_patch.stop)

    async def asyncTearDown(self):
        if self.service_gate is not None:
            self.service_gate.set()
        await self.hass.async_stop(force=True)

    @core.callback
    def _subscribe(self, hass, topic, callback, **kwargs):
        self.subscribed_topics.append(topic)
        self.subscriptions[topic] = callback

        @core.callback
        def unsubscribe():
            self.subscriptions.pop(topic, None)

        return unsubscribe

    async def _record_light(self, call):
        self.light_calls.append(RecordedCall(dict(call.data), time.monotonic(), call.context.id))
        self._call_event.set()
        if self.service_gate is not None:
            await self.service_gate.wait()
        if self.service_error is not None:
            raise self.service_error

    async def _record_click(self, call):
        self.click_calls.append(call.data["label"])
        self._click_event.set()

    def set_light(self, state, **attributes):
        self.hass.states.async_set(ENTITY, state, attributes)

    async def load(self, inputs=None):
        self.assertTrue(BLUEPRINT.is_file(), "IKEA 블루프린트 파일이 필요합니다")
        destination = self.config_dir / "blueprints/automation" / BLUEPRINT_RELATIVE
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BLUEPRINT, destination)
        entry = {"id": "ikea_test", "alias": "IKEA Test", "initial_state": True,
                 "use_blueprint": {"path": BLUEPRINT_RELATIVE, "input": {
                     "knob": "Test Knob", "target_light": ENTITY, **(inputs or {})}}}
        self.config = {"homeassistant": {"latitude": 0, "longitude": 0, "elevation": 0,
                                        "time_zone": "UTC", "unit_system": "metric",
                                        "country": "KR", "currency": "KRW"},
                       "automation": [entry]}
        (self.config_dir / "configuration.yaml").write_text(
            yaml.safe_dump(self.config, allow_unicode=True), encoding="utf-8"
        )
        self.hass.config_entries = config_entries.ConfigEntries(self.hass, self.config)
        await bootstrap.async_load_base_functionality(self.hass)
        self.assertTrue(await async_setup_component(self.hass, "automation", self.config))
        blueprints = automation.async_get_blueprints(self.hass)
        self.blueprint_inputs = await blueprints.async_inputs_from_config(entry)
        self.blueprint = self.blueprint_inputs.blueprint
        await self.hass.async_start()
        await self.hass.async_block_till_done()
        self.automation = self.hass.data[automation.DATA_COMPONENT].get_entity("automation.ikea_test")
        self.assertIsNotNone(self.automation, "실제 HA 자동화가 로딩되어야 합니다")
        self.assertTrue(self.subscriptions, "실제 MQTT 트리거가 구독되어야 합니다")

    async def publish(self, payload, *, topic=None):
        topic = topic or self.subscribed_topics[-1]
        if topic not in self.subscriptions:
            return
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        self.subscriptions[topic](ReceiveMessage(topic, payload, 0, False, topic, time.time()))
        for _ in range(5):
            await asyncio.sleep(0)

    async def _wait_count(self, records, event, count, timeout):
        async with asyncio.timeout(timeout):
            while len(records) < count:
                event.clear()
                await event.wait()

    async def wait_calls(self, count, timeout=3.0):
        await self._wait_count(self.light_calls, self._call_event, count, timeout)

    async def wait_clicks(self, count, timeout=3.0):
        await self._wait_count(self.click_calls, self._click_event, count, timeout)

    async def reload_automations(self):
        await self.hass.services.async_call("automation", "reload", blocking=True)
