import sys
import time

import snap7

PLC_IP = "192.168.0.200"
RACK = 0
SLOT = 1
WARTEZEIT = 10

ZUSTAENDE = {
    "S7CpuStatusRun": "RUN",
    "S7CpuStatusStop": "STOP",
    "S7CpuStatusUnknown": "UNBEKANNT",
}


def zustand(plc: snap7.client.Client) -> str:
    status = plc.get_cpu_state()
    return ZUSTAENDE.get(status, status)


def warte_auf(plc: snap7.client.Client, ziel: str) -> bool:
    for _ in range(WARTEZEIT):
        if zustand(plc) == ziel:
            return True
        time.sleep(1)
    return False


def main() -> int:
    plc = snap7.client.Client()
    try:
        plc.connect(PLC_IP, RACK, SLOT)
        print(f"Verbunden mit SPS {PLC_IP}. Zustand: {zustand(plc)}")

        # STOP hält die Anlage an, daher bewusst bestätigen lassen.
        if input("SPS jetzt in STOP und wieder in RUN versetzen? (j/n): ").strip().lower() != "j":
            print("Abgebrochen.")
            return 0

        plc.plc_stop()
        if not warte_auf(plc, "STOP"):
            print(f"Fehler: SPS ist nach {WARTEZEIT} s nicht in STOP. Zustand: {zustand(plc)}")
            return 1
        print("Zustand: STOP")

        plc.plc_hot_start()
        if not warte_auf(plc, "RUN"):
            print(f"Fehler: SPS ist nach {WARTEZEIT} s nicht in RUN. Zustand: {zustand(plc)}")
            return 1
        print("Zustand: RUN")
        return 0

    except RuntimeError as error:
        print(f"Fehler bei der Kommunikation mit der SPS: {error}")
        print("Prüfen: IP erreichbar? PUT/GET-Zugriff in TIA Portal erlaubt? Schutzstufe 'Vollzugriff'?")
        return 1
    finally:
        if plc.get_connected():
            plc.disconnect()


if __name__ == "__main__":
    sys.exit(main())
