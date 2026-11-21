"""In-memory Meross MRS100 simulator for the H2 functional harness.

It implements the subset of the broker transport used by the adapter and
scheduler: descriptors, GET/SET requests, batched responses and pushes.
"""
from __future__ import annotations

from types import SimpleNamespace

from custom_components.meross_cloud.vendor.merossclient import DeviceDescriptor

STATE = "Appliance.RollerShutter.State"
POSITION = "Appliance.RollerShutter.Position"
CONFIG = "Appliance.RollerShutter.Config"
ADJUST = "Appliance.RollerShutter.Adjust"

MRS100_PAYLOAD = {
    "all": {
        "system": {
            "hardware": {
                "type": "mrs100", "subType": "un", "version": "7.0.0",
                "uuid": "u1", "macAddress": "AA:BB:CC:DD:EE:FF",
            },
            "firmware": {"version": "7.3.3"},
            "online": {"status": 1},
        },
        "digest": {"togglex": [{"channel": 0, "onoff": 1}]},
    },
    "ability": {
        STATE: {},
        POSITION: {},
        CONFIG: {},
        ADJUST: {},
    },
}


class MRS100Simulator:
    uuid = "u1"
    connected = True

    def __init__(self):
        self.position = 0
        self.state = 0
        self.config = {"signalOpen": 45000, "signalClose": 50000}
        self.adjust = 0
        self.adjust_value = 0
        self.bus = None
        self.requests = []
        self.multiples = []

    async def async_connect(self):
        return None

    async def async_stop(self):
        return None

    async def async_describe(self, device_uuid):
        return DeviceDescriptor(MRS100_PAYLOAD)

    def _apply_set(self, namespace, payload):
        if namespace == POSITION:
            position = (payload.get("position") or {}).get("position")
            if position is not None:
                if position == -1:
                    self.state = 0
                else:
                    self.position = int(position)
                    self.state = 1 if int(position) > 0 else 2
        elif namespace == CONFIG:
            config = payload.get("config") or {}
            self.config.update({
                key: config[key] for key in ("signalOpen", "signalClose")
                if key in config})
        elif namespace == ADJUST:
            adjust = payload.get("adjust") or {}
            self.adjust_value = adjust.get("value", 0)
            self.adjust = self.adjust_value

    def _body(self, namespace):
        if namespace == STATE:
            return {"state": [{"channel": 0, "state": self.state}]}
        if namespace == POSITION:
            return {"position": [{"channel": 0, "position": self.position}]}
        if namespace == CONFIG:
            return {"config": [
                {"channel": 0, **dict(self.config)}]}
        if namespace == ADJUST:
            return {"adjust": [{"channel": 0, "status": self.adjust}]}
        return {}

    async def async_request(self, uuid, namespace, method, payload):
        self.requests.append((uuid, namespace, method, payload))
        if method == "SET":
            self._apply_set(namespace, payload)
            body = self._body(namespace)
        else:
            body = self._body(namespace)
        return SimpleNamespace(
            uuid=uuid, namespace=namespace,
            method="SETACK" if method == "SET" else "GETACK",
            payload=body)

    async def async_request_multiple(self, uuid, requests):
        requests = list(requests)
        self.multiples.append(requests)
        return SimpleNamespace(
            uuid=uuid, namespace="Appliance.Control.Multiple",
            method="SETACK",
            payload={"multiple": [{
                "header": {"namespace": namespace, "method": "GETACK"},
                "payload": self._body(namespace),
            } for namespace, _, _ in requests]})

    def emit(self, namespace, payload, method="PUSH"):
        if self.bus is not None:
            self.bus.publish(self.uuid, namespace, payload, method)

    def push(self, adapter, namespace, payload, method="PUSH"):
        adapter._dispatch_message(SimpleNamespace(
            uuid=self.uuid, namespace=namespace, method=method,
            payload=payload))


class MSS310Simulator:
    uuid = "u1"
    connected = True

    def __init__(self, uuid="u1"):
        self.uuid = uuid
        self.onoff = 1
        self.power = 10
        self.voltage = 2300
        self.current = 50
        self.bus = None
        self.requests = []
        self.multiples = []

    async def async_connect(self):
        return None

    async def async_stop(self):
        return None

    async def async_describe(self, device_uuid):
        payload = {
            "all": {"system": {
                "hardware": {"type": "mss310", "subType": "un",
                             "version": "1.0.0", "uuid": self.uuid,
                             "macAddress": "AA:BB:CC:DD:EE:FF"},
                "firmware": {"version": "3.0.0"},
                "online": {"status": 1},
            }, "digest": {"togglex": [{"channel": 0,
                                       "onoff": self.onoff}]}},
            "ability": {"Appliance.Control.ToggleX": {},
                        "Appliance.Control.Electricity": {}},
        }
        return DeviceDescriptor(payload)

    def _body(self, namespace):
        if namespace == "Appliance.Control.ToggleX":
            return {"channel": 0,
                    "togglex": [{"channel": 0, "onoff": self.onoff}]}
        if namespace == "Appliance.Control.Electricity":
            return {"channel": 0, "electricity": {
                "power": self.power, "voltage": self.voltage,
                "current": self.current}}
        return {}

    async def async_request(self, uuid, namespace, method, payload):
        self.requests.append((uuid, namespace, method, payload))
        if method == "SET" and namespace == "Appliance.Control.ToggleX":
            entries = payload.get("togglex") or []
            if entries:
                self.onoff = entries[0].get("onoff", self.onoff)
        return SimpleNamespace(
            uuid=uuid, namespace=namespace,
            method="SETACK" if method == "SET" else "GETACK",
            payload=self._body(namespace))

    async def async_request_multiple(self, uuid, requests):
        requests = list(requests)
        self.multiples.append(requests)
        return SimpleNamespace(
            uuid=uuid, namespace="Appliance.Control.Multiple",
            method="SETACK",
            payload={"multiple": [{
                "header": {"namespace": namespace, "method": "GETACK"},
                "payload": self._body(namespace),
            } for namespace, _, _ in requests]})

    def emit(self, namespace, payload, method="PUSH"):
        if self.bus is not None:
            self.bus.publish(self.uuid, namespace, payload, method)


class MSS425Simulator:
    uuid = "strip1"
    connected = True
    NAMESPACE = "Appliance.Control.ToggleX"

    def __init__(self, uuid="strip1"):
        self.uuid = uuid
        self.channels = (0, 1, 2)
        self.onoff = {channel: 1 for channel in self.channels}
        self.bus = None
        self.requests = []
        self.multiples = []

    async def async_connect(self):
        return None

    async def async_stop(self):
        return None

    async def async_describe(self, device_uuid):
        return DeviceDescriptor({
            "all": {"system": {
                "hardware": {"type": "mss425", "subType": "un",
                             "version": "1.0.0", "uuid": self.uuid,
                             "macAddress": "AA:BB:CC:DD:EE:05"},
                "firmware": {"version": "4.0.0"},
                "online": {"status": 1},
            }, "digest": {"togglex": [
                {"channel": channel, "onoff": self.onoff[channel]}
                for channel in self.channels]}},
            "ability": {self.NAMESPACE: {}},
        })

    def _body(self):
        return {"togglex": [
            {"channel": channel, "onoff": self.onoff[channel]}
            for channel in reversed(self.channels)]}

    async def async_request(self, uuid, namespace, method, payload):
        self.requests.append((uuid, namespace, method, payload))
        if method == "SET" and namespace == self.NAMESPACE:
            for entry in payload.get("togglex") or []:
                channel = entry.get("channel")
                if channel in self.onoff and "onoff" in entry:
                    self.onoff[channel] = entry["onoff"]
        return SimpleNamespace(
            uuid=uuid, namespace=namespace,
            method="SETACK" if method == "SET" else "GETACK",
            payload=self._body())

    async def async_request_multiple(self, uuid, requests):
        requests = list(requests)
        self.multiples.append(requests)
        return SimpleNamespace(
            uuid=uuid, namespace="Appliance.Control.Multiple",
            method="SETACK",
            payload={"multiple": [{
                "header": {"namespace": namespace, "method": "GETACK"},
                "payload": self._body(),
            } for namespace, _, _ in requests]})

    def emit(self, method="PUSH"):
        if self.bus is not None:
            self.bus.publish(self.uuid, self.NAMESPACE,
                             self._body(), method)


class HubSimulator:
    uuid = "hub1"
    connected = True

    def __init__(self, uuid="hub1"):
        self.uuid = uuid
        self.bus = None
        self.requests = []
        self.multiples = []
        self.online = 1
        self.temp_hum = {"latestTemperature": 215, "latestHumidity": 553,
                         "voltage": 3000}
        self.sensor_all = {"temperature": 215, "humidity": 553}
        self.valve = {"mode": 1, "room": 44, "currentSet": 40,
                      "heating": 1, "min": 10, "max": 70, "onoff": 1}
        self.door_status = 1
        self.water_leak = 0
        self.smoke_status = 170
        self.water_onoff = 2
        self.water_dura = 1800
        self.wflow = 1

    async def async_connect(self):
        return None

    async def async_stop(self):
        return None

    async def async_describe(self, device_uuid):
        payload = {
            "all": {"system": {
                "hardware": {"type": "msh300", "subType": "un",
                             "version": "1.0.0", "uuid": self.uuid,
                             "macAddress": "AA:BB:CC:DD:EE:01"},
                "firmware": {"version": "3.0.0"},
                "online": {"status": 1},
            }, "digest": {"hub": {"subdevice": [
                {"id": "sub1", "ms100": {}},
                {"id": "sensor1", "ms130": {}},
                {"id": "valve1", "mts100": {}},
                {"id": "door1", "doorWindow": {}},
                {"id": "leak1", "waterLeak": {}},
                {"id": "smoke1", "smokeAlarm": {}},
                {"id": "mst1", "mst": {}},
            ]}}},
            "ability": {
                "Appliance.System.Online": {},
                "Appliance.Hub.Sensor.TempHum": {},
                "Appliance.Hub.Sensor.All": {},
                "Appliance.Hub.Mts100.All": {},
                "Appliance.Hub.Mts100.Mode": {},
                "Appliance.Hub.Mts100.Temperature": {},
                "Appliance.Hub.Sensor.DoorWindow": {},
                "Appliance.Hub.Sensor.WaterLeak": {},
                "Appliance.Hub.Sensor.Smoke": {},
                "Appliance.Control.Water": {},
                "Appliance.Control.WaterEvent": {},
                "Appliance.Config.DeviceCfg": {},
            },
        }
        return DeviceDescriptor(payload)

    def _body(self, namespace):
        if namespace == "Appliance.System.Online":
            return {"online": {"status": self.online}}
        if namespace == "Appliance.Hub.Sensor.TempHum":
            return {"tempHum": [dict(id="sub1", **self.temp_hum)]}
        if namespace == "Appliance.Hub.Sensor.All":
            return {"all": [{
                "id": "sensor1",
                "temperature": {"latest": self.sensor_all["temperature"]},
                "humidity": {"latest": self.sensor_all["humidity"]},
            }]}
        if namespace == "Appliance.Hub.Mts100.All":
            return {"all": [{
                "id": "valve1",
                "mode": {"state": self.valve["mode"]},
                "temperature": {
                    "room": self.valve["room"],
                    "currentSet": self.valve["currentSet"],
                    "heating": self.valve["heating"],
                    "min": self.valve["min"], "max": self.valve["max"],
                },
                "togglex": {"onoff": self.valve["onoff"]},
            }]}
        if namespace == "Appliance.Hub.Sensor.DoorWindow":
            return {"doorWindow": [
                {"id": "door1", "status": self.door_status}]}
        if namespace == "Appliance.Hub.Sensor.WaterLeak":
            return {"waterLeak": [
                {"id": "leak1", "latestWaterLeak": self.water_leak}]}
        if namespace == "Appliance.Hub.Sensor.Smoke":
            return {"smokeAlarm": [
                {"id": "smoke1", "status": self.smoke_status,
                 "interConn": 0}]}
        if namespace == "Appliance.Control.Water":
            return {"control": [{"subId": "mst1",
                                 "onoff": self.water_onoff,
                                 "dura": self.water_dura,
                                 "lmTime": 0}]}
        if namespace == "Appliance.Config.DeviceCfg":
            return {"config": [{"subId": "mst1", "channel": 0,
                                "mstCfg": {"dura": self.water_dura,
                                           "wfm": 1}}]}
        if namespace == "Appliance.Control.WaterEvent":
            return {"waterEvent": [{"subId": "mst1",
                                    "wflow": self.wflow}]}
        if namespace == "Appliance.Hub.Mts100.Mode":
            return {"mode": [{"id": "valve1", "state": self.valve["mode"]}]}
        if namespace == "Appliance.Hub.Mts100.Temperature":
            return {"temperature": [{"id": "valve1",
                                     "currentSet": self.valve["currentSet"]}]}
        return {}

    def _apply_set(self, namespace, payload):
        if namespace == "Appliance.Control.Water":
            for entry in payload.get("control") or []:
                if entry.get("subId") == "mst1" and "onoff" in entry:
                    self.water_onoff = entry["onoff"]
        elif namespace == "Appliance.Config.DeviceCfg":
            for entry in payload.get("config") or []:
                if entry.get("subId") == "mst1":
                    cfg = entry.get("mstCfg") or {}
                    if "dura" in cfg:
                        self.water_dura = cfg["dura"]
        elif namespace == "Appliance.Hub.Mts100.Mode":
            for entry in payload.get("mode") or []:
                if entry.get("id") == "valve1":
                    self.valve["mode"] = entry.get("state", self.valve["mode"])
        elif namespace == "Appliance.Hub.Mts100.Temperature":
            for entry in payload.get("temperature") or []:
                if entry.get("id") == "valve1":
                    self.valve["currentSet"] = entry.get(
                        "currentSet", self.valve["currentSet"])

    async def async_request(self, uuid, namespace, method, payload):
        self.requests.append((uuid, namespace, method, payload))
        if method == "SET":
            self._apply_set(namespace, payload)
        return SimpleNamespace(
            uuid=uuid, namespace=namespace,
            method="SETACK" if method == "SET" else "GETACK",
            payload=self._body(namespace))

    async def async_request_multiple(self, uuid, requests):
        requests = list(requests)
        self.multiples.append(requests)
        return SimpleNamespace(
            uuid=uuid, namespace="Appliance.Control.Multiple",
            method="SETACK",
            payload={"multiple": [{
                "header": {"namespace": namespace, "method": "GETACK"},
                "payload": self._body(namespace),
            } for namespace, _, _ in requests]})

    def emit(self, namespace, payload=None, method="PUSH"):
        if self.bus is not None:
            self.bus.publish(self.uuid, namespace,
                             self._body(namespace) if payload is None
                             else payload, method)

    def push_all(self):
        self.emit("Appliance.Hub.Sensor.TempHum")
        self.emit("Appliance.Hub.Sensor.All")
        self.emit("Appliance.Hub.Mts100.All")
        self.emit("Appliance.Hub.Sensor.DoorWindow")
        self.emit("Appliance.Hub.Sensor.WaterLeak")
        self.emit("Appliance.Hub.Sensor.Smoke")
        self.emit("Appliance.Control.Water")
        self.emit("Appliance.Config.DeviceCfg")
        self.emit("Appliance.Control.WaterEvent")


class MTS200Simulator:
    uuid = "t1"
    connected = True
    NAMESPACE = "Appliance.Control.Thermostat.Mode"

    def __init__(self, uuid="t1"):
        self.uuid = uuid
        self.bus = None
        self.requests = []
        self.multiples = []
        self.state = {"onoff": 1, "mode": 1, "state": 1,
                      "currentTemp": 177, "targetTemp": 200,
                      "min": 50, "max": 350}

    async def async_connect(self):
        return None

    async def async_stop(self):
        return None

    async def async_describe(self, device_uuid):
        return DeviceDescriptor({
            "all": {"system": {
                "hardware": {"type": "mts200", "subType": "un",
                             "version": "1.0.0", "uuid": self.uuid,
                             "macAddress": "AA:BB:CC:DD:EE:02"},
                "firmware": {"version": "3.0.0"},
                "online": {"status": 1},
            }, "digest": {}},
            "ability": {self.NAMESPACE: {}},
        })

    def _body(self):
        return {"mode": [{"channel": 0, **self.state}]}

    async def async_request(self, uuid, namespace, method, payload):
        self.requests.append((uuid, namespace, method, payload))
        if method == "SET" and namespace == self.NAMESPACE:
            for entry in payload.get("mode") or []:
                if entry.get("channel", 0) != 0:
                    continue
                for key in ("onoff", "mode", "targetTemp"):
                    if key in entry:
                        self.state[key] = entry[key]
        return SimpleNamespace(
            uuid=uuid, namespace=namespace,
            method="SETACK" if method == "SET" else "GETACK",
            payload=self._body())

    async def async_request_multiple(self, uuid, requests):
        requests = list(requests)
        self.multiples.append(requests)
        return SimpleNamespace(
            uuid=uuid, namespace="Appliance.Control.Multiple",
            method="SETACK",
            payload={"multiple": [{
                "header": {"namespace": namespace, "method": "GETACK"},
                "payload": self._body() if namespace == self.NAMESPACE
                else {},
            } for namespace, _, _ in requests]})

    def emit(self, method="PUSH"):
        if self.bus is not None:
            self.bus.publish(self.uuid, self.NAMESPACE,
                             self._body(), method)


class LightSimulator:
    uuid = "l1"
    connected = True
    NAMESPACE = "Appliance.Control.Light"

    def __init__(self, uuid="l1"):
        self.uuid = uuid
        self.bus = None
        self.requests = []
        self.multiples = []
        self.state = {"onoff": 1, "luminance": 80, "rgb": 0x123456,
                      "capacity": 4}

    async def async_connect(self):
        return None

    async def async_stop(self):
        return None

    async def async_describe(self, device_uuid):
        return DeviceDescriptor({
            "all": {"system": {
                "hardware": {"type": "msl120", "subType": "un",
                             "version": "1.0.0", "uuid": self.uuid,
                             "macAddress": "AA:BB:CC:DD:EE:03"},
                "firmware": {"version": "3.0.0"},
                "online": {"status": 1},
            }, "digest": {"light": dict(self.state)}},
            "ability": {"Appliance.Control.ToggleX": {},
                        self.NAMESPACE: {}},
        })

    def _body(self):
        return {"channel": 0, "light": dict(self.state)}

    async def async_request(self, uuid, namespace, method, payload):
        self.requests.append((uuid, namespace, method, payload))
        if method == "SET" and namespace == self.NAMESPACE:
            for key in ("onoff", "luminance", "rgb"):
                if key in payload.get("light", {}):
                    self.state[key] = payload["light"][key]
        return SimpleNamespace(
            uuid=uuid, namespace=namespace,
            method="SETACK" if method == "SET" else "GETACK",
            payload=self._body())

    async def async_request_multiple(self, uuid, requests):
        requests = list(requests)
        self.multiples.append(requests)
        return SimpleNamespace(
            uuid=uuid, namespace="Appliance.Control.Multiple",
            method="SETACK",
            payload={"multiple": [{
                "header": {"namespace": namespace, "method": "GETACK"},
                "payload": self._body() if namespace == self.NAMESPACE
                else {},
            } for namespace, _, _ in requests]})

    def emit(self, method="PUSH"):
        if self.bus is not None:
            self.bus.publish(self.uuid, self.NAMESPACE,
                             self._body(), method)


class DiffuserSimulator:
    uuid = "d1"
    connected = True
    SPRAY = "Appliance.Control.Diffuser.Spray"
    LIGHT = "Appliance.Control.Diffuser.Light"

    def __init__(self, uuid="d1"):
        self.uuid = uuid
        self.bus = None
        self.requests = []
        self.multiples = []
        self.spray_mode = 1
        self.light = {"onoff": 1, "luminance": 50, "rgb": 100}

    async def async_connect(self):
        return None

    async def async_stop(self):
        return None

    async def async_describe(self, device_uuid):
        return DeviceDescriptor({
            "all": {"system": {
                "hardware": {"type": "mod", "subType": "un",
                             "version": "1.0.0", "uuid": self.uuid,
                             "macAddress": "AA:BB:CC:DD:EE:04"},
                "firmware": {"version": "3.0.0"},
                "online": {"status": 1},
            }, "digest": {"light": dict(self.light),
                          "spray": {"mode": self.spray_mode}}},
            "ability": {self.SPRAY: {}, self.LIGHT: {}},
        })

    def _body(self, namespace):
        if namespace == self.SPRAY:
            return {"spray": {"channel": 0, "mode": self.spray_mode}}
        if namespace == self.LIGHT:
            return {"channel": 0, "light": dict(self.light)}
        return {}

    async def async_request(self, uuid, namespace, method, payload):
        self.requests.append((uuid, namespace, method, payload))
        if method == "SET" and namespace == self.SPRAY:
            self.spray_mode = payload.get("spray", {}).get(
                "mode", self.spray_mode)
        elif method == "SET" and namespace == self.LIGHT:
            for key in ("onoff", "luminance", "rgb"):
                if key in payload.get("light", {}):
                    self.light[key] = payload["light"][key]
        return SimpleNamespace(
            uuid=uuid, namespace=namespace,
            method="SETACK" if method == "SET" else "GETACK",
            payload=self._body(namespace))

    async def async_request_multiple(self, uuid, requests):
        requests = list(requests)
        self.multiples.append(requests)
        return SimpleNamespace(
            uuid=uuid, namespace="Appliance.Control.Multiple",
            method="SETACK",
            payload={"multiple": [{
                "header": {"namespace": namespace, "method": "GETACK"},
                "payload": self._body(namespace),
            } for namespace, _, _ in requests]})

    def emit(self, namespace, method="PUSH"):
        if self.bus is not None:
            self.bus.publish(self.uuid, namespace,
                             self._body(namespace), method)


class MTS300Simulator(MTS200Simulator):
    uuid = "t3"

    def __init__(self, uuid="t3"):
        super().__init__(uuid)
        self.state = {"onoff": 1, "mode": 1, "state": 1,
                      "currentTemp": 1770, "targetTemp": 2000,
                      "min": 500, "max": 3500}

    async def async_describe(self, device_uuid):
        return DeviceDescriptor({
            "all": {"system": {
                "hardware": {"type": "mts300", "subType": "un",
                             "version": "1.0.0", "uuid": self.uuid,
                             "macAddress": "AA:BB:CC:DD:EE:06"},
                "firmware": {"version": "3.0.0"},
                "online": {"status": 1},
            }, "digest": {}},
            "ability": {self.NAMESPACE: {}},
        })


class MS600Simulator:
    uuid = "p1"
    connected = True
    NAMESPACE = "Appliance.Control.Sensor.LatestX"

    def __init__(self, uuid="p1"):
        self.uuid = uuid
        self.bus = None
        self.requests = []
        self.multiples = []
        self.presence = {"value": 2, "distance": 760, "times": 0}
        self.light = 24

    async def async_connect(self):
        return None

    async def async_stop(self):
        return None

    async def async_describe(self, device_uuid):
        return DeviceDescriptor({
            "all": {"system": {
                "hardware": {"type": "ms600", "subType": "un",
                             "version": "1.0.0", "uuid": self.uuid,
                             "macAddress": "AA:BB:CC:DD:EE:07"},
                "firmware": {"version": "3.0.0"},
                "online": {"status": 1},
            }, "digest": {"light": {"value": self.light}}},
            "ability": {self.NAMESPACE: {}},
        })

    def _body(self):
        return {"latest": [{"channel": 0, "data": {
            "presence": [dict(self.presence)],
            "light": [{"value": self.light}],
        }}]}

    async def async_request(self, uuid, namespace, method, payload):
        self.requests.append((uuid, namespace, method, payload))
        return SimpleNamespace(
            uuid=uuid, namespace=namespace,
            method="SETACK" if method == "SET" else "GETACK",
            payload=self._body())

    async def async_request_multiple(self, uuid, requests):
        requests = list(requests)
        self.multiples.append(requests)
        return SimpleNamespace(
            uuid=uuid, namespace="Appliance.Control.Multiple",
            method="SETACK",
            payload={"multiple": [{
                "header": {"namespace": namespace, "method": "GETACK"},
                "payload": self._body(),
            } for namespace, _, _ in requests]})

    def emit(self, method="PUSH"):
        if self.bus is not None:
            self.bus.publish(self.uuid, self.NAMESPACE,
                             self._body(), method)


class GarageSimulator:
    uuid = "g1"
    connected = True
    NAMESPACE = "Appliance.GarageDoor.State"

    def __init__(self, uuid="g1"):
        self.uuid = uuid
        self.open = 0
        self.bus = None
        self.requests = []
        self.multiples = []

    async def async_connect(self):
        return None

    async def async_stop(self):
        return None

    async def async_describe(self, device_uuid):
        return DeviceDescriptor({
            "all": {"system": {
                "hardware": {"type": "msg", "subType": "un",
                             "version": "4.0.0", "uuid": self.uuid,
                             "macAddress": "AA:BB:CC:DD:EE:08"},
                "firmware": {"version": "4.2.8"},
                "online": {"status": 1},
            }, "digest": {"garageDoor": [
                {"channel": 0, "open": self.open}]}},
            "ability": {self.NAMESPACE: {}},
        })

    def _body(self):
        return {"state": [{"channel": 0, "open": self.open,
                           "lmTime": 0}]}

    async def async_request(self, uuid, namespace, method, payload):
        self.requests.append((uuid, namespace, method, payload))
        if method == "SET" and namespace == self.NAMESPACE:
            state = payload.get("state") or {}
            if "open" in state:
                self.open = state["open"]
        return SimpleNamespace(
            uuid=uuid, namespace=namespace,
            method="SETACK" if method == "SET" else "GETACK",
            payload=self._body())

    async def async_request_multiple(self, uuid, requests):
        requests = list(requests)
        self.multiples.append(requests)
        return SimpleNamespace(
            uuid=uuid, namespace="Appliance.Control.Multiple",
            method="SETACK",
            payload={"multiple": [{
                "header": {"namespace": namespace, "method": "GETACK"},
                "payload": self._body(),
            } for namespace, _, _ in requests]})

    def emit(self, method="PUSH"):
        if self.bus is not None:
            self.bus.publish(self.uuid, self.NAMESPACE,
                             self._body(), method)


class Map100Simulator:
    uuid = "pur1"
    connected = True
    FAN = "Appliance.Control.Fan"
    FILTER = "Appliance.Control.FilterMaintenance"

    def __init__(self, uuid="pur1"):
        self.uuid = uuid
        self.speed = 1
        self.max_speed = 1
        self.life = 73
        self.bus = None
        self.requests = []
        self.multiples = []

    async def async_connect(self):
        return None

    async def async_stop(self):
        return None

    async def async_describe(self, device_uuid):
        return DeviceDescriptor({
            "all": {"system": {
                "hardware": {"type": "map", "subType": "un",
                             "version": "3.0.0", "uuid": self.uuid,
                             "macAddress": "AA:BB:CC:DD:EE:09"},
                "firmware": {"version": "3.1.5"},
                "online": {"status": 1},
            }, "digest": {"fan": [{"channel": 0, "speed": self.speed,
                                   "maxSpeed": self.max_speed}]}},
            "ability": {self.FAN: {}, self.FILTER: {},
                        "Appliance.Control.ToggleX": {}},
        })

    def _body(self, namespace):
        if namespace == self.FAN:
            return {"fan": [{"channel": 0, "speed": self.speed,
                             "maxSpeed": self.max_speed}]}
        if namespace == self.FILTER:
            return {"filter": [{"channel": 0, "life": self.life}]}
        return {}

    async def async_request(self, uuid, namespace, method, payload):
        self.requests.append((uuid, namespace, method, payload))
        if method == "SET" and namespace == self.FAN:
            for entry in payload.get("fan") or []:
                if entry.get("channel", 0) == 0 and "speed" in entry:
                    self.speed = entry["speed"]
        return SimpleNamespace(
            uuid=uuid, namespace=namespace,
            method="SETACK" if method == "SET" else "GETACK",
            payload=self._body(namespace))

    async def async_request_multiple(self, uuid, requests):
        requests = list(requests)
        self.multiples.append(requests)
        return SimpleNamespace(
            uuid=uuid, namespace="Appliance.Control.Multiple",
            method="SETACK",
            payload={"multiple": [{
                "header": {"namespace": namespace, "method": "GETACK"},
                "payload": self._body(namespace),
            } for namespace, _, _ in requests]})

    def emit(self, method="PUSH"):
        if self.bus is not None:
            for namespace in (self.FAN, self.FILTER):
                self.bus.publish(self.uuid, namespace,
                                 self._body(namespace), method)


class EMSimulator:
    uuid = "em1"
    connected = True
    NS = "Appliance.Control.ElectricityX"

    def __init__(self, uuid="em1"):
        self.uuid = uuid
        self.bus = None
        self.requests = []
        self.multiples = []
        self.channels = {
            1: {"power": 300, "voltage": 229000, "current": 1300,
                "mConsume": 12000, "factor": 0.95},
            2: {"power": 1200, "voltage": 230000, "current": 5200,
                "mConsume": 45000, "factor": 0.98},
        }

    async def async_connect(self):
        return None

    async def async_stop(self):
        return None

    async def async_describe(self, device_uuid):
        return DeviceDescriptor({
            "all": {"system": {
                "hardware": {"type": "em06", "subType": "eu",
                             "version": "2.0.0", "uuid": self.uuid,
                             "macAddress": "AA:BB:CC:DD:EE:0A"},
                "firmware": {"version": "2.3.8"},
                "online": {"status": 1},
            }, "digest": {"electricityx": [
                {"channel": channel} for channel in self.channels]}},
            "ability": {self.NS: {}},
        })

    def _body(self):
        return {"electricityx": [
            {"channel": channel, **values}
            for channel, values in self.channels.items()]}

    async def async_request(self, uuid, namespace, method, payload):
        self.requests.append((uuid, namespace, method, payload))
        return SimpleNamespace(
            uuid=uuid, namespace=namespace,
            method="SETACK" if method == "SET" else "GETACK",
            payload=self._body())

    async def async_request_multiple(self, uuid, requests):
        requests = list(requests)
        self.multiples.append(requests)
        return SimpleNamespace(
            uuid=uuid, namespace="Appliance.Control.Multiple",
            method="SETACK",
            payload={"multiple": [{
                "header": {"namespace": namespace, "method": "GETACK"},
                "payload": self._body(),
            } for namespace, _, _ in requests]})

    def emit(self, method="PUSH"):
        if self.bus is not None:
            self.bus.publish(self.uuid, self.NS, self._body(), method)


class Msxh0Simulator:
    uuid = "sx1"
    connected = True
    SPRAY = "Appliance.Control.Spray"
    LIGHT = "Appliance.Control.Light"

    def __init__(self, uuid="sx1"):
        self.uuid = uuid
        self.bus = None
        self.requests = []
        self.multiples = []
        self.mode = 0
        self.light = {"onoff": 0, "luminance": 100, "rgb": 0x102030}

    async def async_connect(self):
        return None

    async def async_stop(self):
        return None

    async def async_describe(self, device_uuid):
        return DeviceDescriptor({
            "all": {"system": {
                "hardware": {"type": "msxh0", "subType": "us",
                             "version": "3.0.0", "uuid": self.uuid,
                             "macAddress": "AA:BB:CC:DD:EE:0B"},
                "firmware": {"version": "3.1.5"},
                "online": {"status": 1},
            }, "digest": {"spray": {"channel": 0, "mode": self.mode},
                          "light": {"channel": 0, **self.light}}},
            "ability": {self.SPRAY: {}, self.LIGHT: {}},
        })

    def _body(self, namespace):
        if namespace == self.SPRAY:
            return {"spray": {"channel": 0, "mode": self.mode}}
        if namespace == self.LIGHT:
            return {"channel": 0, "light": dict(self.light)}
        return {}

    async def async_request(self, uuid, namespace, method, payload):
        self.requests.append((uuid, namespace, method, payload))
        if method == "SET" and namespace == self.SPRAY:
            self.mode = (payload.get("spray") or {}).get("mode", self.mode)
        elif method == "SET" and namespace == self.LIGHT:
            for key in ("onoff", "luminance", "rgb"):
                if key in payload.get("light", {}):
                    self.light[key] = payload["light"][key]
        return SimpleNamespace(
            uuid=uuid, namespace=namespace,
            method="SETACK" if method == "SET" else "GETACK",
            payload=self._body(namespace))

    async def async_request_multiple(self, uuid, requests):
        requests = list(requests)
        self.multiples.append(requests)
        return SimpleNamespace(
            uuid=uuid, namespace="Appliance.Control.Multiple",
            method="SETACK",
            payload={"multiple": [{
                "header": {"namespace": namespace, "method": "GETACK"},
                "payload": self._body(namespace),
            } for namespace, _, _ in requests]})

    def emit(self, method="PUSH"):
        if self.bus is not None:
            for namespace in (self.SPRAY, self.LIGHT):
                self.bus.publish(self.uuid, namespace,
                                 self._body(namespace), method)


class HP110Simulator:
    uuid = "hp1"
    connected = True
    TOGGLE = "Appliance.Control.ToggleX"
    LIGHT = "Appliance.Control.Light"

    def __init__(self, uuid="hp1"):
        self.uuid = uuid
        self.bus = None
        self.requests = []
        self.multiples = []
        self.onoff = 0
        self.light = {"onoff": 0, "luminance": 20, "rgb": 0x050207}

    async def async_connect(self):
        return None

    async def async_stop(self):
        return None

    async def async_describe(self, device_uuid):
        return DeviceDescriptor({
            "all": {"system": {
                "hardware": {"type": "hp110ahk", "subType": "un",
                             "version": "4.0.0", "uuid": self.uuid,
                             "macAddress": "AA:BB:CC:DD:EE:0C"},
                "firmware": {"version": "4.1.12"},
                "online": {"status": 1},
            }, "digest": {"togglex": [{"channel": 0,
                                       "onoff": self.onoff}],
                          "light": {"channel": 0, **self.light}}},
            "ability": {self.TOGGLE: {}, self.LIGHT: {}},
        })

    def _body(self, namespace):
        if namespace == self.TOGGLE:
            return {"channel": 0,
                    "togglex": [{"channel": 0, "onoff": self.onoff}]}
        if namespace == self.LIGHT:
            return {"channel": 0, "light": dict(self.light)}
        return {}

    async def async_request(self, uuid, namespace, method, payload):
        self.requests.append((uuid, namespace, method, payload))
        if method == "SET" and namespace == self.TOGGLE:
            entries = payload.get("togglex") or []
            if entries:
                self.onoff = entries[0].get("onoff", self.onoff)
        elif method == "SET" and namespace == self.LIGHT:
            for key in ("onoff", "luminance", "rgb"):
                if key in payload.get("light", {}):
                    self.light[key] = payload["light"][key]
        return SimpleNamespace(
            uuid=uuid, namespace=namespace,
            method="SETACK" if method == "SET" else "GETACK",
            payload=self._body(namespace))

    async def async_request_multiple(self, uuid, requests):
        requests = list(requests)
        self.multiples.append(requests)
        return SimpleNamespace(
            uuid=uuid, namespace="Appliance.Control.Multiple",
            method="SETACK",
            payload={"multiple": [{
                "header": {"namespace": namespace, "method": "GETACK"},
                "payload": self._body(namespace),
            } for namespace, _, _ in requests]})

    def emit(self, method="PUSH"):
        if self.bus is not None:
            for namespace in (self.TOGGLE, self.LIGHT):
                self.bus.publish(self.uuid, namespace,
                                 self._body(namespace), method)
