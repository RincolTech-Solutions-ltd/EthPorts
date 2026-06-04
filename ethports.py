#!/usr/bin/env python3
"""ethports — Ethernet IP management and connectivity toolkit."""

import sys
import os
import re
import json
import getpass
import ipaddress
import subprocess
import shutil
from pathlib import Path

# ── ANSI colours ──────────────────────────────────────────────────────────────
R     = "\033[0m";  BOLD = "\033[1m";  DIM  = "\033[2m"
RED   = "\033[91m"; GREEN= "\033[92m"; YEL  = "\033[93m"
CYAN  = "\033[96m"; WHITE= "\033[97m"; GRAY = "\033[90m"

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_DIR    = Path.home() / ".config" / "ethports"
PROFILES_FILE = CONFIG_DIR / "profiles.json"
BW = 56  # banner width

SKIP_PREFIXES = ("lo", "wl", "ww", "vir", "dock", "br", "veth", "tun", "tap", "dummy")


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def banner() -> None:
    line  = "─" * BW
    title = "🌐  EthPorts"
    print(f"\n{CYAN}{BOLD}  ╭{line}╮{R}")
    print(f"{CYAN}{BOLD}  │{title:^{BW}}│{R}")
    print(f"{CYAN}{BOLD}  ╰{line}╯{R}\n")


def step(label: str) -> None:
    """Print step label without newline — caller appends ✓ or ✗."""
    print(f"  {CYAN}[{label}]{R} ", end="", flush=True)


def ok(msg: str = "") -> None:
    suffix = f"  {DIM}{msg}{R}" if msg else ""
    print(f"{GREEN}{BOLD}✓{R}{suffix}")


def fail(msg: str = "") -> None:
    print(f"{RED}{BOLD}✗{R}" + (f"  {RED}{msg}{R}" if msg else ""))


def warn(msg: str) -> None:
    print(f"  {YEL}⚠  {msg}{R}")


def hint(msg: str) -> None:
    print(f"  {DIM}{msg}{R}")


def die(msg: str) -> None:
    print(f"\n  {RED}{BOLD}✗  {msg}{R}\n")
    sys.exit(1)


def divider() -> None:
    print(f"  {GRAY}{'─' * BW}{R}")


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def has(binary: str) -> bool:
    return shutil.which(binary) is not None


# ══════════════════════════════════════════════════════════════════════════════
# Interface helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_eth_interfaces() -> list[str]:
    result = run(["ip", "link", "show"])
    ifaces = []
    for line in result.stdout.splitlines():
        m = re.match(r"^\d+:\s+(\S+):", line)
        if m:
            name = m.group(1).rstrip("@")
            if not any(name.startswith(p) for p in SKIP_PREFIXES):
                ifaces.append(name)
    return ifaces


def get_iface_ips(iface: str) -> list[str]:
    result = run(["ip", "addr", "show", iface])
    return re.findall(r"inet (\d+\.\d+\.\d+\.\d+/\d+)", result.stdout)


def get_iface_state(iface: str) -> str:
    result = run(["ip", "link", "show", iface])
    if "state UP" in result.stdout:
        return "UP"
    if "state DOWN" in result.stdout:
        return "DOWN"
    return "UNKNOWN"


def get_iface_mac(iface: str) -> str:
    result = run(["ip", "link", "show", iface])
    m = re.search(r"link/ether\s+(\S+)", result.stdout)
    return m.group(1) if m else "—"


def get_iface_mtu(iface: str) -> str:
    result = run(["ip", "link", "show", iface])
    m = re.search(r"mtu (\d+)", result.stdout)
    return m.group(1) if m else "—"


def state_label(state: str) -> str:
    if state == "UP":
        return f"{GREEN}{BOLD}UP{R}"
    if state == "DOWN":
        return f"{RED}{BOLD}DOWN{R}"
    return f"{GRAY}?{R}"


def pick_iface(ifaces: list[str], prompt: str = "Select interface") -> str:
    if len(ifaces) == 1:
        return ifaces[0]
    if not ifaces:
        die("No ethernet interfaces found.")

    print(f"  {BOLD}{GRAY}#    {'Interface':<26} State{R}")
    divider()
    for i, iface in enumerate(ifaces, 1):
        s = get_iface_state(iface)
        print(f"  {CYAN}{BOLD}{i:<4}{R} {WHITE}{iface:<26}{R} {state_label(s)}")
    print()
    while True:
        try:
            raw = input(f"  {CYAN}{BOLD}{prompt} [1–{len(ifaces)}]:{R} ").strip()
            idx = int(raw)
            if 1 <= idx <= len(ifaces):
                return ifaces[idx - 1]
            print(f"  {YEL}Enter a number between 1 and {len(ifaces)}.{R}")
        except ValueError:
            print(f"  {YEL}Enter a number.{R}")
        except KeyboardInterrupt:
            print(f"\n  {GRAY}Cancelled.{R}\n")
            sys.exit(0)


def validate_cidr(cidr: str) -> bool:
    try:
        ipaddress.ip_interface(cidr)
        return True
    except ValueError:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# RDP profile store
# ══════════════════════════════════════════════════════════════════════════════

def load_profiles() -> dict:
    if PROFILES_FILE.exists():
        try:
            return json.loads(PROFILES_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_profiles(profiles: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_FILE.write_text(json.dumps(profiles, indent=2))


# ══════════════════════════════════════════════════════════════════════════════
# Commands
# ══════════════════════════════════════════════════════════════════════════════

def cmd_list(_args: list[str]) -> None:
    banner()
    ifaces = get_eth_interfaces()
    if not ifaces:
        print(f"  {RED}No ethernet interfaces found.{R}\n")
        return

    col_i, col_m = 26, 20
    print(f"  {BOLD}{GRAY}{'Interface':<{col_i}} {'State':<10} {'MAC':<{col_m}} IPs{R}")
    divider()
    for iface in ifaces:
        state  = get_iface_state(iface)
        mac    = get_iface_mac(iface)
        ips    = get_iface_ips(iface)
        sl     = state_label(state)
        ip_str = f"{WHITE}{', '.join(ips)}{R}" if ips else f"{GRAY}(no IPs){R}"
        print(f"  {CYAN}{BOLD}{iface:<{col_i}}{R} {sl:<18} {WHITE}{mac:<{col_m}}{R} {ip_str}")
    print()


def cmd_add(args: list[str]) -> None:
    banner()
    if not args:
        die("Usage: ethports add <ip/prefix> [iface]\n  Example: ethports add 192.168.1.50/24")

    cidr = args[0]
    if not validate_cidr(cidr):
        die(f"Invalid address: {cidr}  —  use CIDR format e.g. 192.168.1.50/24")

    ifaces = get_eth_interfaces()
    if len(args) >= 2:
        iface = args[1]
        if iface not in ifaces:
            die(f"Interface not found: {iface}")
    else:
        iface = pick_iface(ifaces, "Add IP to")

    step("add")
    print(f"{WHITE}{cidr}{R} → {WHITE}{iface}{R}...", end="", flush=True)
    r = run(["ip", "addr", "add", cidr, "dev", iface])
    if r.returncode == 0:
        ok()
        warn("IP is temporary and will be lost on reboot.")
        hint("For persistence: configure NetworkManager or netplan.")
    else:
        fail(r.stderr.strip())
        sys.exit(1)
    print()


def cmd_remove(args: list[str]) -> None:
    banner()
    if not args:
        die("Usage: ethports remove <ip/prefix> [iface]\n  Example: ethports remove 192.168.1.50/24")

    cidr = args[0]
    if not validate_cidr(cidr):
        die(f"Invalid address: {cidr}")

    ifaces = get_eth_interfaces()
    if len(args) >= 2:
        iface = args[1]
        if iface not in ifaces:
            die(f"Interface not found: {iface}")
    else:
        iface = pick_iface(ifaces, "Remove from")

    step("remove")
    print(f"{WHITE}{cidr}{R} from {WHITE}{iface}{R}...", end="", flush=True)
    r = run(["ip", "addr", "del", cidr, "dev", iface])
    if r.returncode == 0:
        ok()
    else:
        fail(r.stderr.strip())
        sys.exit(1)
    print()


def cmd_flush(args: list[str]) -> None:
    banner()
    ifaces = get_eth_interfaces()
    iface  = args[0] if args else pick_iface(ifaces, "Flush interface")
    if iface not in ifaces:
        die(f"Interface not found: {iface}")

    ips = get_iface_ips(iface)
    if not ips:
        print(f"  {GRAY}No IPs on {iface}.{R}\n")
        return

    print(f"  {DIM}Removing {len(ips)} IP(s) from {iface}...{R}\n")
    fail_n = 0
    for ip in ips:
        step("flush")
        print(f"{WHITE}{ip}{R}...", end="", flush=True)
        r = run(["ip", "addr", "del", ip, "dev", iface])
        if r.returncode == 0:
            ok()
        else:
            fail(r.stderr.strip())
            fail_n += 1

    print()
    divider()
    if fail_n == 0:
        print(f"  {GREEN}{BOLD}✓ All {len(ips)} IP(s) removed from {iface}{R}")
    else:
        print(f"  {RED}{BOLD}✗ {fail_n} failed{R}   {GREEN}✓ {len(ips)-fail_n} removed{R}")
    print()


def cmd_up(args: list[str]) -> None:
    banner()
    ifaces = get_eth_interfaces()
    iface  = args[0] if args else pick_iface(ifaces, "Bring up")
    if iface not in ifaces:
        die(f"Interface not found: {iface}")

    step("up")
    print(f"Bringing up {WHITE}{iface}{R}...", end="", flush=True)
    r = run(["ip", "link", "set", iface, "up"])
    if r.returncode == 0:
        ok()
    else:
        fail(r.stderr.strip())
        sys.exit(1)
    print()


def cmd_down(args: list[str]) -> None:
    banner()
    ifaces = get_eth_interfaces()
    iface  = args[0] if args else pick_iface(ifaces, "Take down")
    if iface not in ifaces:
        die(f"Interface not found: {iface}")

    step("down")
    print(f"Taking down {WHITE}{iface}{R}...", end="", flush=True)
    r = run(["ip", "link", "set", iface, "down"])
    if r.returncode == 0:
        ok()
    else:
        fail(r.stderr.strip())
        sys.exit(1)
    print()


def cmd_info(args: list[str]) -> None:
    banner()
    ifaces = get_eth_interfaces()
    iface  = args[0] if args else pick_iface(ifaces, "Interface info")
    if iface not in ifaces:
        die(f"Interface not found: {iface}")

    state = get_iface_state(iface)
    mac   = get_iface_mac(iface)
    mtu   = get_iface_mtu(iface)
    ips   = get_iface_ips(iface)

    print(f"  {BOLD}{WHITE}{iface}{R}\n")
    print(f"  {GRAY}State   :{R}  {state_label(state)}")
    print(f"  {GRAY}MAC     :{R}  {WHITE}{mac}{R}")
    print(f"  {GRAY}MTU     :{R}  {WHITE}{mtu}{R}")

    if ips:
        for i, ip in enumerate(ips):
            label = "IPs     :" if i == 0 else "         "
            print(f"  {GRAY}{label}{R}  {WHITE}{ip}{R}")
    else:
        print(f"  {GRAY}IPs     :{R}  {GRAY}(none){R}")

    if has("ethtool"):
        r = run(["ethtool", iface])
        if r.returncode == 0:
            print()
            interested = {"Speed", "Duplex", "Auto-negotiation", "Link detected"}
            for line in r.stdout.splitlines():
                line = line.strip()
                for key in interested:
                    if line.startswith(key):
                        _, _, val = line.partition(":")
                        val = val.strip()
                        if val.lower() in ("yes", "full", "10000mb/s", "1000mb/s", "100mb/s"):
                            vc = GREEN
                        elif val.lower() in ("no", "half"):
                            vc = RED
                        else:
                            vc = WHITE
                        print(f"  {GRAY}{key:<20}:{R}  {vc}{val}{R}")
    print()


def cmd_scan(args: list[str]) -> None:
    banner()
    ifaces = get_eth_interfaces()
    iface  = args[0] if args else pick_iface(ifaces, "Scan on")
    if iface not in ifaces:
        die(f"Interface not found: {iface}")

    ips = get_iface_ips(iface)
    if not ips:
        die(f"No IP assigned to {iface} — cannot determine subnet")

    network = str(ipaddress.ip_interface(ips[0]).network)
    print(f"  {DIM}Scanning {network} on {iface}...{R}\n")

    if has("nmap"):
        r = run(["nmap", "-sn", network, "--oG", "-"])
        hosts = []
        for line in r.stdout.splitlines():
            m = re.search(r"Host:\s+(\S+)\s+\(([^)]*)\)", line)
            if m and "Status: Up" in line:
                hosts.append((m.group(1), m.group(2) or "—"))

        if not hosts:
            print(f"  {GRAY}No hosts found.{R}\n")
            return

        col = 20
        print(f"  {BOLD}{GRAY}#    {'IP Address':<{col}} Hostname{R}")
        divider()
        for i, (ip, hostname) in enumerate(hosts, 1):
            print(f"  {CYAN}{BOLD}{i:<4}{R} {WHITE}{ip:<{col}}{R} {GRAY}{hostname}{R}")
        print()
        print(f"  {GREEN}{BOLD}✓ {len(hosts)} host(s) found{R}\n")

    elif has("arp-scan"):
        r = run(["arp-scan", f"--interface={iface}", "--localnet"])
        hosts = []
        for line in r.stdout.splitlines():
            m = re.match(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f:]+)\s+(.*)", line)
            if m:
                hosts.append((m.group(1), m.group(2), m.group(3).strip()))

        if not hosts:
            print(f"  {GRAY}No hosts found.{R}\n")
            return

        col_ip, col_mac = 20, 20
        print(f"  {BOLD}{GRAY}#    {'IP':<{col_ip}} {'MAC':<{col_mac}} Vendor{R}")
        divider()
        for i, (ip, mac, vendor) in enumerate(hosts, 1):
            print(f"  {CYAN}{BOLD}{i:<4}{R} {WHITE}{ip:<{col_ip}}{R} {WHITE}{mac:<{col_mac}}{R} {GRAY}{vendor}{R}")
        print()
        print(f"  {GREEN}{BOLD}✓ {len(hosts)} host(s) found{R}\n")

    else:
        warn("nmap or arp-scan required for network scanning.")
        hint("Install:  sudo apt install nmap")
        print()


def cmd_rdp(args: list[str]) -> None:
    banner()

    # ── list profiles ──────────────────────────────────────────────────────────
    if args and args[0] == "list":
        profiles = load_profiles()
        if not profiles:
            print(f"  {GRAY}No saved RDP profiles.{R}\n")
            hint("Save one:  ethports rdp save <name> <host>")
            print()
            return
        col = 18
        print(f"  {BOLD}{GRAY}#    {'Name':<{col}} {'Host':<22} User{R}")
        divider()
        for i, (name, data) in enumerate(profiles.items(), 1):
            host = data.get("host", "—")
            user = data.get("user", "—")
            print(f"  {CYAN}{BOLD}{i:<4}{R} {WHITE}{name:<{col}}{R} {WHITE}{host:<22}{R} {GRAY}{user}{R}")
        print()
        return

    # ── save profile ───────────────────────────────────────────────────────────
    if args and args[0] == "save":
        if len(args) < 3:
            die("Usage: ethports rdp save <name> <host>")
        name, host = args[1], args[2]
        try:
            user = input(f"  {CYAN}Windows username for {WHITE}{host}{R}{CYAN}:{R} ").strip()
        except KeyboardInterrupt:
            print(f"\n  {GRAY}Cancelled.{R}\n")
            sys.exit(0)
        profiles      = load_profiles()
        profiles[name] = {"host": host, "user": user}
        save_profiles(profiles)
        step("save")
        print(f"Profile {WHITE}{name}{R} ({host})...", end="", flush=True)
        ok()
        print()
        return

    # ── delete profile ─────────────────────────────────────────────────────────
    if args and args[0] == "delete":
        if len(args) < 2:
            die("Usage: ethports rdp delete <name>")
        name     = args[1]
        profiles = load_profiles()
        if name not in profiles:
            die(f"Profile not found: {name}")
        del profiles[name]
        save_profiles(profiles)
        step("delete")
        print(f"Profile {WHITE}{name}{R}...", end="", flush=True)
        ok()
        print()
        return

    # ── connect ────────────────────────────────────────────────────────────────
    rdp_bin = next((b for b in ("xfreerdp3", "xfreerdp") if has(b)), None)
    if not rdp_bin:
        warn("xfreerdp is not installed.")
        hint("Install:  sudo apt install freerdp2-x11")
        print()
        sys.exit(1)

    host = user = None

    if args:
        target   = args[0]
        profiles = load_profiles()
        if target in profiles:
            host = profiles[target]["host"]
            user = profiles[target].get("user", "")
            print(f"  {DIM}Profile: {target} → {host}{R}\n")
        else:
            host = target

    try:
        if not host:
            host = input(f"  {CYAN}{BOLD}Windows host / IP:{R} ").strip()
        if not user:
            user = input(f"  {CYAN}Username:{R} ").strip()
        password = getpass.getpass(f"  {CYAN}Password:{R} ")
    except KeyboardInterrupt:
        print(f"\n  {GRAY}Cancelled.{R}\n")
        sys.exit(0)

    print(f"\n  {DIM}Connecting to {WHITE}{host}{DIM} as {WHITE}{user}{DIM}...{R}\n")

    cmd = [
        rdp_bin,
        f"/v:{host}",
        f"/u:{user}",
        f"/p:{password}",
        "/dynamic-resolution",
        "/cert:ignore",
        "+clipboard",
        "/audio-mode:0",
    ]

    result = subprocess.run(cmd)
    print()
    if result.returncode == 0:
        print(f"  {GREEN}{BOLD}✓ Session ended.{R}\n")
    else:
        print(f"  {RED}{BOLD}✗ Connection failed (exit {result.returncode}).{R}")
        hint("Check: RDP is enabled on Windows, port 3389 is open,")
        hint("and the host is reachable from this machine.")
        print()


def cmd_gateway(args: list[str]) -> None:
    sub = args[0].lower() if args else "show"

    # Escalate before banner so it only prints once
    if sub in ("set", "del", "delete") and os.geteuid() != 0:
        os.execvp("sudo", ["sudo", sys.executable] + sys.argv)

    banner()

    # ── show ───────────────────────────────────────────────────────────────────
    if sub == "show" or (sub not in ("set", "del", "delete") and not args):
        result = run(["ip", "route", "show", "default"])
        lines  = [l for l in result.stdout.splitlines() if l.strip()]
        if not lines:
            print(f"  {GRAY}No default gateway configured.{R}\n")
            hint("Set one:  ethports gateway set <gw> [iface]")
            print()
            return

        col_gw, col_if = 20, 20
        print(f"  {BOLD}{GRAY}{'Gateway':<{col_gw}} {'Interface':<{col_if}} Metric{R}")
        divider()
        for line in lines:
            gw  = re.search(r"via (\S+)", line)
            dev = re.search(r"dev (\S+)", line)
            met = re.search(r"metric (\d+)", line)
            gw_s  = gw.group(1)  if gw  else "—"
            dev_s = dev.group(1) if dev else "—"
            met_s = met.group(1) if met else "—"
            print(f"  {WHITE}{gw_s:<{col_gw}}{R} {CYAN}{BOLD}{dev_s:<{col_if}}{R} {GRAY}{met_s}{R}")
        print()
        return

    # ── set ────────────────────────────────────────────────────────────────────
    if sub == "set":
        if len(args) < 2:
            die("Usage: ethports gateway set <gateway> [iface]\n  Example: ethports gateway set 192.168.1.1")
        gw    = args[1]
        iface = args[2] if len(args) >= 3 else None

        try:
            ipaddress.ip_address(gw)
        except ValueError:
            die(f"Invalid gateway address: {gw}")

        cmd = ["ip", "route", "replace", "default", "via", gw]
        if iface:
            cmd += ["dev", iface]

        step("gateway")
        label = f"{WHITE}{gw}{R}" + (f" via {WHITE}{iface}{R}" if iface else "")
        print(f"Setting default gateway {label}...", end="", flush=True)
        r = run(cmd)
        if r.returncode == 0:
            ok()
            warn("Gateway change is temporary and will be lost on reboot.")
        else:
            fail(r.stderr.strip())
            sys.exit(1)
        print()
        return

    # ── del ────────────────────────────────────────────────────────────────────
    if sub in ("del", "delete"):
        gw  = args[1] if len(args) >= 2 else None
        cmd = ["ip", "route", "del", "default"]
        if gw:
            cmd += ["via", gw]

        step("gateway")
        label = f"via {WHITE}{gw}{R}" if gw else f"{WHITE}default route{R}"
        print(f"Removing {label}...", end="", flush=True)
        r = run(cmd)
        if r.returncode == 0:
            ok()
        else:
            fail(r.stderr.strip())
            sys.exit(1)
        print()
        return

    die(f"Unknown gateway subcommand: {sub}\n  Use: show | set | del")


def cmd_help(_args: list[str]) -> None:
    banner()

    def section(title: str) -> None:
        print(f"  {BOLD}{CYAN}{title}{R}")
        print(f"  {GRAY}{'─' * 54}{R}")

    def row(cmd: str, desc: str) -> None:
        print(f"  {WHITE}{cmd:<38}{R} {GRAY}{desc}{R}")

    section("IP Management")
    row("ethports list",                       "All interfaces: state, MAC, IPs")
    row("ethports add <ip/prefix> [iface]",    "Add IPv4 address")
    row("ethports remove <ip/prefix> [iface]", "Remove IPv4 address  (alias: rm)")
    row("ethports flush [iface]",              "Remove all IPs from an interface")
    print()

    section("Interface Control")
    row("ethports up <iface>",                 "Bring interface up")
    row("ethports down <iface>",               "Bring interface down")
    row("ethports info [iface]",               "Speed, duplex, MTU, MAC, driver")
    print()

    section("Network Discovery")
    row("ethports scan [iface]",               "ARP scan — find live hosts on subnet")
    print()

    section("Gateway")
    row("ethports gateway",                    "Show current default gateway(s)")
    row("ethports gateway set <gw> [iface]",   "Set default gateway")
    row("ethports gateway del [gw]",           "Remove default gateway")
    print()

    section("Remote Desktop  (RDP → Windows)")
    row("ethports rdp <host>",                 "Open RDP session")
    row("ethports rdp save <name> <host>",     "Save a connection profile")
    row("ethports rdp list",                   "Show saved profiles")
    row("ethports rdp delete <name>",          "Remove a saved profile")
    print()

    section("Help")
    row("ethports help",                       "Show this guide")
    print()

    print(f"  {BOLD}{GRAY}Examples{R}")
    print(f"  {GRAY}{'─' * 54}{R}")
    examples = [
        ("ethports list",                          "See all interfaces at a glance"),
        ("ethports add 192.168.1.50/24",           "Add IP, pick interface interactively"),
        ("ethports add 10.0.0.5/8 enp2s0",         "Add IP to a specific interface"),
        ("ethports remove 192.168.1.50/24 enp2s0", "Remove a specific IP"),
        ("ethports flush enp2s0",                  "Wipe all IPs from enp2s0"),
        ("ethports scan enp2s0",                   "Discover devices on the subnet"),
        ("ethports gateway",                       "Show default gateway"),
        ("ethports gateway set 192.168.1.1",       "Set gateway (auto-picks interface)"),
        ("ethports gateway set 10.0.0.1 enp2s0",  "Set gateway on specific interface"),
        ("ethports gateway del",                   "Remove default gateway"),
        ("ethports rdp 192.168.1.100",             "RDP into a Windows host"),
        ("ethports rdp save office 10.0.0.50",     "Save profile named 'office'"),
        ("ethports rdp office",                    "Connect via saved profile"),
    ]
    for cmd, desc in examples:
        print(f"  {DIM}${R} {WHITE}{cmd:<42}{R} {GRAY}# {desc}{R}")
    print()

    print(f"  {BOLD}{GRAY}Notes{R}")
    print(f"  {GRAY}{'─' * 54}{R}")
    print(f"  {DIM}• IP changes via add/remove/flush are temporary (lost on reboot).{R}")
    print(f"  {DIM}• add/remove/flush/up/down/gateway set|del require root — ethports escalates automatically.{R}")
    print(f"  {DIM}• scan requires nmap or arp-scan  (sudo apt install nmap).{R}")
    print(f"  {DIM}• rdp requires xfreerdp           (sudo apt install freerdp2-x11).{R}")
    print()


# ══════════════════════════════════════════════════════════════════════════════
# Dispatch
# ══════════════════════════════════════════════════════════════════════════════

COMMANDS: dict[str, callable] = {
    "list":    cmd_list,
    "add":     cmd_add,
    "remove":  cmd_remove,
    "rm":      cmd_remove,
    "flush":   cmd_flush,
    "up":      cmd_up,
    "down":    cmd_down,
    "info":    cmd_info,
    "scan":    cmd_scan,
    "gateway": cmd_gateway,
    "gw":      cmd_gateway,
    "rdp":     cmd_rdp,
    "help":    cmd_help,
    "--help":  cmd_help,
    "-h":      cmd_help,
}

PRIVILEGED = {"add", "remove", "rm", "flush", "up", "down"}
# gateway handles its own escalation internally (only set/del need root)


def main() -> None:
    if len(sys.argv) < 2:
        cmd_help([])
        sys.exit(0)

    verb = sys.argv[1].lower()

    # Escalate before any output so the banner only prints once
    if verb in PRIVILEGED and os.geteuid() != 0:
        os.execvp("sudo", ["sudo", sys.executable] + sys.argv)

    if verb not in COMMANDS:
        print(f"\n  {RED}Unknown command:{R} {WHITE}{verb}{R}")
        hint("Run:  ethports help")
        print()
        sys.exit(1)

    COMMANDS[verb](sys.argv[2:])


if __name__ == "__main__":
    main()
