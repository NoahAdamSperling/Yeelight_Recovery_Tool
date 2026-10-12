"""

Yeelight Complete Recovery / LAN Control Utility

=================================================



Purpose

-------

This utility can:



1. Find an already-configured Yeelight on the current LAN.

2. Recover its current IP address and miIO token using the miIO

   discovery handshake.

3. Identify the bulb's model and firmware.

4. Check whether Yeelight LAN/developer mode is already enabled.

5. Attempt to enable LAN Control using multiple methods.

6. Check Yeelight UDP discovery as an optional diagnostic.

7. Verify TCP port 55443 as the Yeelight control channel.

8. Verify the Yeelight JSON LAN protocol and use it as the authoritative LAN-control test.

9. If the bulb is factory-reset, find its setup Wi-Fi network,

   connect to it, configure home Wi-Fi, and then repeat discovery.



Important

---------

Run PowerShell or VS Code as Administrator.



Requirements

------------

Windows 10/11

Python 3.10+

python-miio 0.5.12



Install:



    python -m pip install python-miio==0.5.12



Security

--------

- Wi-Fi passwords are entered using getpass.

- Wi-Fi passwords are never printed.

- The bulb token is not printed.

- Token is saved locally to Desktop/yeelight_token.txt.

- Recovery information is saved to Desktop/yeelight_recovery_info.txt.

"""



import ctypes

import getpass

import hashlib

import ipaddress

import json

import os

import re

import socket

import subprocess

import sys

import time

import xml.sax.saxutils as saxutils



from concurrent.futures import ThreadPoolExecutor, as_completed





# ============================================================

# CONFIGURATION

# ============================================================



SETUP_IP = "10.10.1.1"



MIIO_PORT = 54321

YEELIGHT_PORT = 55443



TEMP_PC_IP = "10.10.1.2"

TEMP_NETMASK = "255.255.255.0"



YEELIGHT_DISCOVERY_IP = "239.255.255.250"

YEELIGHT_DISCOVERY_PORT = 1982



SETUP_SSID_PREFIXES = (

    "yeelink-light-",

    "yeelight-",

)



SCAN_MAX_WORKERS = 48



HOME_DISCOVERY_TIMEOUT = 60



TOKEN_FILE = os.path.join(

    os.path.expanduser("~"),

    "Desktop",

    "yeelight_token.txt",

)



RECOVERY_FILE = os.path.join(

    os.path.expanduser("~"),

    "Desktop",

    "yeelight_recovery_info.txt",

)





# ============================================================

# DISPLAY

# ============================================================



def banner(title):

    print()

    print("=" * 78)

    print(f" {title}")

    print("=" * 78)

    print()





def step(message):

    print()

    print("=" * 78)

    print(f" {message}")

    print("=" * 78)





def info(message):

    print(f"[INFO]    {message}")





def success(message):

    print(f"[SUCCESS] {message}")





def warning(message):

    print(f"[WARNING] {message}")





def failed(message):

    print(f"[FAILED]  {message}")





# ============================================================

# ADMIN

# ============================================================



def is_admin():

    try:

        return bool(

            ctypes.windll.shell32.IsUserAnAdmin()

        )

    except Exception:

        return False





def require_admin():

    if not is_admin():

        banner(

            "ADMINISTRATOR PRIVILEGES REQUIRED"

        )



        print(

            "This script changes the Windows Wi-Fi adapter "

            "during factory-reset recovery."

        )



        print()

        print(

            "Please run PowerShell or VS Code as Administrator."

        )

        print()



        input(

            "Press Enter to exit..."

        )



        sys.exit(1)





# ============================================================

# WINDOWS COMMANDS

# ============================================================



def run_command(

    command,

    timeout=30,

):

    try:



        result = subprocess.run(

            command,

            capture_output=True,

            text=True,

            timeout=timeout,

            shell=False,

        )



        return (

            result.returncode,

            result.stdout,

            result.stderr,

        )



    except subprocess.TimeoutExpired:

        return (

            -1,

            "",

            "Command timed out",

        )



    except Exception as exc:

        return (

            -1,

            "",

            str(exc),

        )





# ============================================================

# WIFI INTERFACE

# ============================================================



def get_wifi_interface():



    code, stdout, stderr = run_command(

        [

            "netsh",

            "wlan",

            "show",

            "interfaces",

        ]

    )



    if code != 0:

        return None



    for line in stdout.splitlines():



        line = line.strip()



        if line.lower().startswith("name"):



            parts = line.split(

                ":",

                1,

            )



            if len(parts) == 2:



                name = parts[1].strip()



                if name:

                    return name



    return None





def get_current_wifi_ssid():



    code, stdout, stderr = run_command(

        [

            "netsh",

            "wlan",

            "show",

            "interfaces",

        ]

    )



    if code != 0:

        return None



    for line in stdout.splitlines():



        line = line.strip()



        if (

            line.lower().startswith("ssid")

            and not line.lower().startswith("bssid")

        ):



            parts = line.split(

                ":",

                1,

            )



            if len(parts) == 2:



                ssid = parts[1].strip()



                if ssid:

                    return ssid



    return None





# ============================================================

# WIFI SCANNING

# ============================================================



def scan_wifi():



    info(

        "Scanning for visible Wi-Fi networks..."

    )



    code, stdout, stderr = run_command(

        [

            "netsh",

            "wlan",

            "show",

            "networks",

            "mode=bssid",

        ],

        timeout=30,

    )



    if code != 0:



        failed(

            "Could not scan Wi-Fi networks."

        )



        if stderr:

            print(stderr)



        return []



    networks = []



    for raw_line in stdout.splitlines():



        line = raw_line.strip()



        if (

            line.startswith("SSID ")

            and ":" in line

        ):



            match = re.match(

                r"SSID\s+\d+\s*:\s*(.*)",

                line,

            )



            if match:



                ssid = match.group(1).strip()



                if ssid:

                    networks.append(ssid)



    unique = []



    for ssid in networks:



        if ssid not in unique:

            unique.append(ssid)



    return unique





def find_setup_networks():



    networks = scan_wifi()



    matches = []



    for ssid in networks:



        lower = ssid.lower()



        if any(

            lower.startswith(prefix)

            for prefix in SETUP_SSID_PREFIXES

        ):



            matches.append(ssid)



    return matches





# ============================================================

# WIFI PROFILE

# ============================================================



def create_open_wifi_profile(

    ssid,

):



    escaped_ssid = saxutils.escape(

        ssid

    )



    xml = f"""<?xml version="1.0"?>

<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">

    <name>{escaped_ssid}</name>

    <SSIDConfig>

        <SSID>

            <name>{escaped_ssid}</name>

        </SSID>

    </SSIDConfig>

    <connectionType>ESS</connectionType>

    <connectionMode>manual</connectionMode>

    <MSM>

        <security>

            <authEncryption>

                <authentication>open</authentication>

                <encryption>none</encryption>

                <useOneX>false</useOneX>

            </authEncryption>

        </security>

    </MSM>

</WLANProfile>

"""



    temp_file = os.path.join(

        os.environ.get(

            "TEMP",

            ".",

        ),

        "yeelight_setup_profile.xml",

    )



    try:



        with open(

            temp_file,

            "w",

            encoding="utf-8",

        ) as f:



            f.write(xml)



        code, stdout, stderr = run_command(

            [

                "netsh",

                "wlan",

                "add",

                "profile",

                f"filename={temp_file}",

                "user=current",

            ]

        )



        return code == 0



    finally:



        try:

            os.remove(temp_file)

        except Exception:

            pass





def connect_wifi(

    ssid,

    wait_seconds=25,

):



    info(

        f"Connecting to Wi-Fi network: {ssid}"

    )



    code, stdout, stderr = run_command(

        [

            "netsh",

            "wlan",

            "connect",

            f"name={ssid}",

        ],

        timeout=30,

    )



    if code != 0:



        info(

            "Existing Windows Wi-Fi profile was not available."

        )



        info(

            "Creating a temporary open Wi-Fi profile..."

        )



        if not create_open_wifi_profile(

            ssid

        ):



            warning(

                "Could not create the temporary Wi-Fi profile."

            )



        code, stdout, stderr = run_command(

            [

                "netsh",

                "wlan",

                "connect",

                f"name={ssid}",

            ],

            timeout=30,

        )



    if code != 0:



        failed(

            f"Could not start Wi-Fi connection to {ssid}."

        )



        if stderr:

            print(stderr)



        return False



    for _ in range(

        wait_seconds

    ):



        time.sleep(1)



        current = get_current_wifi_ssid()



        if current == ssid:



            success(

                f"Connected to {ssid}"

            )



            return True



    if get_current_wifi_ssid() == ssid:



        success(

            f"Connected to {ssid}"

        )



        return True



    failed(

        "Windows did not confirm the expected Wi-Fi connection."

    )



    return False





# ============================================================

# WINDOWS IPV4 INFORMATION

# ============================================================



def get_interface_ipv4(

    interface,

):



    code, stdout, stderr = run_command(

        [

            "netsh",

            "interface",

            "ipv4",

            "show",

            "addresses",

            f"name={interface}",

        ]

    )



    if code != 0:

        return []



    addresses = []



    for line in stdout.splitlines():



        match = re.search(

            r"IP Address:\s*"

            r"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",

            line,

            re.IGNORECASE,

        )



        if match:



            addresses.append(

                match.group(1)

            )



    return addresses





def get_ipv4_network(

    interface,

):



    code, stdout, stderr = run_command(

        [

            "netsh",

            "interface",

            "ipv4",

            "show",

            "addresses",

            f"name={interface}",

        ]

    )



    if code != 0:

        return None



    # Newer Windows output may contain:

    #

    # Subnet Prefix: 192.168.68.0/24

    #

    match = re.search(

        r"Subnet Prefix:\s*"

        r"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)"

        r"/(\d+)",

        stdout,

        re.IGNORECASE,

    )



    if match:



        try:



            return ipaddress.ip_network(

                f"{match.group(1)}/{match.group(2)}",

                strict=False,

            )



        except Exception:

            pass



    # Fallback: use the first IPv4 address and assume /24.

    addresses = get_interface_ipv4(

        interface

    )



    for address in addresses:



        try:



            return ipaddress.ip_network(

                f"{address}/24",

                strict=False,

            )



        except Exception:

            pass



    return None





def get_local_ipv4(

    interface,

):



    addresses = get_interface_ipv4(

        interface

    )



    for address in addresses:



        try:



            ip = ipaddress.ip_address(

                address

            )



            if (

                ip.version == 4

                and not ip.is_loopback

                and not ip.is_link_local

                and not ip.is_unspecified

            ):



                return str(ip)



        except Exception:

            pass



    return None





# ============================================================

# TEMPORARY SETUP NETWORK

# ============================================================



def configure_temporary_setup_ip(

    interface,

):



    step(

        "CONFIGURE PC FOR YEELIGHT SETUP NETWORK"

    )



    addresses = get_interface_ipv4(

        interface

    )



    already_correct = any(

        address.startswith("10.10.1.")

        for address in addresses

    )



    if already_correct:



        success(

            "PC is already configured for 10.10.1.0/24."

        )



        return True



    info(

        f"Assigning {TEMP_PC_IP}/{TEMP_NETMASK}"

    )



    code, stdout, stderr = run_command(

        [

            "netsh",

            "interface",

            "ipv4",

            "set",

            "address",

            f"name={interface}",

            "source=static",

            f"address={TEMP_PC_IP}",

            f"mask={TEMP_NETMASK}",

            "gateway=none",

        ],

        timeout=30,

    )



    if code != 0:



        failed(

            "Windows could not assign the temporary setup IP."

        )



        if stderr:

            print(stderr)



        return False



    time.sleep(2)



    addresses = get_interface_ipv4(

        interface

    )



    if TEMP_PC_IP in addresses:



        success(

            f"Temporary IP {TEMP_PC_IP} assigned."

        )



        return True



    failed(

        "Temporary setup IP was not confirmed."

    )



    return False





def restore_dhcp(

    interface,

):



    step(

        "RESTORE NORMAL WIFI CONFIGURATION"

    )



    info(

        "Returning Wi-Fi adapter to DHCP..."

    )



    code, stdout, stderr = run_command(

        [

            "netsh",

            "interface",

            "ipv4",

            "set",

            "address",

            f"name={interface}",

            "source=dhcp",

        ],

        timeout=30,

    )



    if code != 0:



        warning(

            "Primary DHCP restore command failed."

        )



        ps_command = (

            f'Set-NetIPInterface '

            f'-InterfaceAlias "{interface}" '

            f'-Dhcp Enabled'

        )



        ps_code, ps_stdout, ps_stderr = run_command(

            [

                "powershell.exe",

                "-NoProfile",

                "-ExecutionPolicy",

                "Bypass",

                "-Command",

                ps_command,

            ],

            timeout=30,

        )



        if ps_code == 0:



            success(

                "DHCP restored through PowerShell."

            )



        else:



            warning(

                "PowerShell DHCP restoration also failed."

            )



            if ps_stderr:

                print(ps_stderr)



    else:



        success(

            "IPv4 DHCP restored."

        )



    run_command(

        [

            "netsh",

            "interface",

            "ipv4",

            "set",

            "dnsservers",

            f"name={interface}",

            "source=dhcp",

        ],

        timeout=30,

    )



    info(

        "Refreshing DHCP lease..."

    )



    run_command(

        [

            "ipconfig",

            "/release",

            interface,

        ],

        timeout=30,

    )



    time.sleep(2)



    run_command(

        [

            "ipconfig",

            "/renew",

            interface,

        ],

        timeout=60,

    )



    time.sleep(4)



    addresses = get_interface_ipv4(

        interface

    )



    for address in addresses:

        print(

            f"    {address}"

        )





# ============================================================

# ============================================================

# TOKEN VALIDATION / RECOVERY
# ============================================================


def is_valid_miio_token(token):
    if token is None:
        return False
    token = str(token).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        return False
    return token not in ("0" * 32, "f" * 32)


def load_saved_token():
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            token = f.read().strip()
        return token if is_valid_miio_token(token) else None
    except Exception:
        return None


def try_cloud_token(device_id=None, mac_address=None, model=None):
    step("RECOVER REAL TOKEN FROM XIAOMI CLOUD")
    try:
        from miio.cloud import CloudInterface
    except Exception:
        warning("Xiaomi Cloud support is unavailable because micloud is not installed.")
        info("Install it with: python -m pip install micloud")
        return None
    info("The bulb's miIO handshake returned a hidden token.")
    info("Credentials are used only for this lookup and are not saved by this script.")
    username = input("Xiaomi/Mi Home email or phone: ").strip()
    if not username:
        return None
    password = getpass.getpass("Xiaomi/Mi Home password: ")
    locale = input("Xiaomi Cloud locale [us]: ").strip().lower() or "us"
    try:
        cloud = CloudInterface(username=username, password=password)
        devices = cloud.get_devices(locale=locale)
        wanted_id = str(device_id) if device_id else None
        wanted_mac = (mac_address or "").replace(":", "").replace("-", "").lower()
        candidates = []
        for device in devices.values():
            token = getattr(device, "token", None)
            if not is_valid_miio_token(token):
                continue
            did = str(getattr(device, "did", ""))
            dev_mac = str(getattr(device, "mac", "")).replace(":", "").replace("-", "").lower()
            dev_model = str(getattr(device, "model", ""))
            if wanted_id and did == wanted_id:
                candidates.insert(0, token)
            elif wanted_mac and dev_mac == wanted_mac:
                candidates.insert(0, token)
            elif model and dev_model == str(model):
                candidates.append(token)
        if candidates:
            token = str(candidates[0]).strip().lower()
            success("A valid 32-character token was recovered from Xiaomi Cloud.")
            return token
        warning("No matching device with a valid token was returned by Xiaomi Cloud.")
    except Exception as exc:
        warning(f"Xiaomi Cloud token lookup failed: {exc}")
    return None

# ============================================================

# MIIO HELLO

# ============================================================



def miio_hello(

    ip,

    timeout=1.5,

):



    hello = bytes.fromhex(

        "21310020"

        "ffffffffffffffffffffffffffffffffffffffff"

        "ffffffffffffffff"

    )



    sock = socket.socket(

        socket.AF_INET,

        socket.SOCK_DGRAM,

    )



    try:



        sock.settimeout(

            timeout

        )



        sock.sendto(

            hello,

            (

                ip,

                MIIO_PORT,

            ),

        )



        data, addr = sock.recvfrom(

            1024

        )



        if len(data) < 32:

            return None



        device_id = data[

            8:12

        ].hex()



        token = data[

            16:32

        ].hex()



        
        if not is_valid_miio_token(token):
            token = None

        return {

            "ip": addr[0],

            "device_id": device_id,

            "token": token,

        }



    except Exception:

        return None



    finally:

        sock.close()





# ============================================================

# MIIO SUBNET DISCOVERY

# ============================================================



def discover_miio_devices(

    network,

    show_progress=True,

):



    if not network:

        return []



    hosts = list(

        network.hosts()

    )



    # Avoid accidentally scanning enormous networks.

    if len(hosts) > 1024:



        warning(

            f"Network {network} contains {len(hosts)} hosts."

        )



        warning(

            "Limiting discovery to the first 1024 addresses."

        )



        hosts = hosts[:1024]



    info(

        f"Scanning {network} for miIO devices..."

    )



    found = []



    with ThreadPoolExecutor(

        max_workers=SCAN_MAX_WORKERS

    ) as executor:



        futures = {

            executor.submit(

                miio_hello,

                str(address),

            ): str(address)

            for address in hosts

        }



        for future in as_completed(

            futures

        ):



            try:



                result = future.result()



                if result is not None:



                    found.append(

                        result

                    )



                    success(

                        "miIO device found at "

                        f"{result['ip']} "

                        f"(ID {result['device_id']})"

                    )



            except Exception:

                pass



    return found





def find_known_device(

    network,

    expected_device_id=None,

):



    devices = discover_miio_devices(

        network

    )



    if not devices:

        return None



    if expected_device_id:



        for device in devices:



            if (

                device["device_id"]

                == expected_device_id

            ):



                return device



    if len(devices) == 1:

        return devices[0]



    print()



    print(

        "Multiple miIO devices were found:"

    )



    for index, device in enumerate(

        devices,

        1,

    ):



        print(

            f"    {index}. "

            f"{device['ip']} "

            f"(ID {device['device_id']})"

        )



    choice = input(

        "Select the Yeelight device number: "

    ).strip()



    try:



        selected = devices[

            int(choice) - 1

        ]



        return selected



    except Exception:



        warning(

            "Invalid selection."

        )



        return None





# ============================================================

# PYTHON-MIIO

# ============================================================



def import_miio():



    try:



        from miio import Yeelight



        return Yeelight



    except ImportError:



        failed(

            "python-miio is not installed."

        )



        print()



        print(

            f'"{sys.executable}" '

            f'-m pip install python-miio==0.5.12'

        )



        return None





# ============================================================

# MIIO DEVICE INFORMATION

# ============================================================



def get_miio_device_info(

    ip,

    token,

):



    Yeelight = import_miio()



    if Yeelight is None:

        return None



    step(

        "IDENTIFY YEELIGHT"

    )



    try:



        bulb = Yeelight(

            ip=ip,

            token=token,

        )



        info(

            "Requesting miIO device information..."

        )



        device_info = bulb.info()



        result = {}



        # DeviceInfo is normally a dataclass-like object.

        for field in (

            "model",

            "firmware_version",

            "hardware_version",

            "mac_address",

            "device_id",

            "life",

            "wifi_ssid",

            "wifi_rssi",

            "token",

        ):



            try:



                value = getattr(

                    device_info,

                    field,

                    None,

                )



                if value is not None:



                    result[field] = str(

                        value

                    )



            except Exception:

                pass



        print()



        if result.get("model"):

            print(

                f"Model:           {result['model']}"

            )



        if result.get("firmware_version"):

            print(

                f"Firmware:        {result['firmware_version']}"

            )



        if result.get("hardware_version"):

            print(

                f"Hardware:        {result['hardware_version']}"

            )



        if result.get("mac_address"):

            print(

                f"MAC:             {result['mac_address']}"

            )



        success(

            "miIO device information retrieved."

        )



        return result



    except Exception as exc:



        warning(

            "Could not retrieve complete miIO device information."

        )



        info(

            f"python-miio reported: {exc}"

        )



        return None





# ============================================================

# YEELIGHT STATUS

# ============================================================



def get_yeelight_status(

    ip,

    token,

):



    Yeelight = import_miio()



    if Yeelight is None:

        return None



    try:



        bulb = Yeelight(

            ip=ip,

            token=token,

        )



        status = bulb.status()



        return status



    except Exception as exc:



        warning(

            f"Could not retrieve Yeelight status: {exc}"

        )



        return None





def extract_developer_mode(

    status,

):



    if status is None:

        return None



    # python-miio's Yeelight status normally exposes

    # developer_mode.

    for name in (

        "developer_mode",

        "lan_ctrl",

    ):



        try:



            value = getattr(

                status,

                name,

                None,

            )



            if value is not None:

                return bool(value)



        except Exception:

            pass



    # Fall back to dictionary-like status.

    if isinstance(

        status,

        dict,

    ):



        for name in (

            "developer_mode",

            "lan_ctrl",

        ):



            if name in status:

                return bool(

                    status[name]

                )



    return None





def check_lan_control(

    ip,

    token,

):



    info(

        "Checking current Yeelight LAN/developer mode..."

    )



    status = get_yeelight_status(

        ip,

        token,

    )



    value = extract_developer_mode(

        status

    )



    if value is True:



        success(

            "LAN/developer mode is currently ENABLED."

        )



    elif value is False:



        warning(

            "LAN/developer mode is currently DISABLED."

        )



    else:



        warning(

            "Could not determine current LAN-control state."

        )



    return value





# ============================================================

# ENABLE LAN CONTROL

# ============================================================



def try_python_miio_developer_mode(

    ip,

    token,

):



    Yeelight = import_miio()



    if Yeelight is None:

        return False



    info(

        "Method 1: python-miio set_developer_mode(True)"

    )



    try:



        bulb = Yeelight(

            ip=ip,

            token=token,

        )



        if not hasattr(

            bulb,

            "set_developer_mode",

        ):



            warning(

                "Installed python-miio does not expose "

                "set_developer_mode()."

            )



            return False



        result = bulb.set_developer_mode(

            True

        )



        success(

            f"python-miio returned: {result}"

        )



        return True



    except Exception as exc:



        warning(

            "python-miio set_developer_mode() failed."

        )



        info(

            f"Error: {exc}"

        )



        return False





def try_raw_set_ps(

    ip,

    token,

):



    Yeelight = import_miio()



    if Yeelight is None:

        return False



    info(

        "Method 2: direct miIO set_ps(cfg_lan_ctrl, 1)"

    )



    try:



        bulb = Yeelight(

            ip=ip,

            token=token,

        )



        # set_developer_mode() ultimately uses this command

        # in python-miio. Calling it directly gives us the

        # raw device response rather than hiding it.

        result = bulb.send(

            "set_ps",

            [

                "cfg_lan_ctrl",

                "1",

            ],

        )



        print(

            f"Raw set_ps response: {result}"

        )



        if (

            result

            and (

                result == ["ok"]

                or "ok" in result

            )

        ):



            success(

                "Direct set_ps command returned OK."

            )



            return True



        warning(

            "Direct set_ps command returned an unexpected response."

        )



        return False



    except Exception as exc:



        warning(

            "Direct set_ps command failed."

        )



        info(

            f"Error: {exc}"

        )



        return False





def enable_lan_control(

    ip,

    token,

):



    step(

        "ENABLE YEELIGHT LAN CONTROL"

    )



    before = check_lan_control(

        ip,

        token,

    )



    if before is True:



        success(

            "LAN Control is already enabled."

        )



        return True



    # --------------------------------------------------------

    # Method 1

    # --------------------------------------------------------



    method1 = try_python_miio_developer_mode(

        ip,

        token,

    )



    time.sleep(3)



    after1 = check_lan_control(

        ip,

        token,

    )



    if after1 is True:



        success(

            "LAN Control is confirmed ENABLED."

        )



        return True



    # --------------------------------------------------------

    # Method 2

    # --------------------------------------------------------



    method2 = try_raw_set_ps(

        ip,

        token,

    )



    time.sleep(3)



    after2 = check_lan_control(

        ip,

        token,

    )



    if after2 is True:



        success(

            "LAN Control is confirmed ENABLED "

            "after direct set_ps."

        )



        return True



    # --------------------------------------------------------

    # Final diagnostic

    # --------------------------------------------------------



    warning(

        "Neither LAN-Control method produced a confirmed "

        "enabled state."

    )



    if not method1:

        warning(

            "python-miio method did not succeed."

        )



    if not method2:

        warning(

            "Direct set_ps method did not succeed."

        )



    return False





# ============================================================

# YEELIGHT UDP DISCOVERY

# ============================================================



def yeelight_udp_discovery(

    timeout=5,

):



    info(

        "Testing Yeelight UDP discovery on "

        "239.255.255.250:1982..."

    )



    message = (

        "M-SEARCH * HTTP/1.1\r\n"

        "HOST: 239.255.255.250:1982\r\n"

        'MAN: "ssdp:discover"\r\n'

        "ST: wifi_bulb\r\n"

        "\r\n"

    ).encode(

        "utf-8"

    )



    sock = socket.socket(

        socket.AF_INET,

        socket.SOCK_DGRAM,

        socket.IPPROTO_UDP,

    )



    try:



        sock.setsockopt(

            socket.SOL_SOCKET,

            socket.SO_REUSEADDR,

            1,

        )



        sock.settimeout(

            timeout

        )



        sock.sendto(

            message,

            (

                YEELIGHT_DISCOVERY_IP,

                YEELIGHT_DISCOVERY_PORT,

            ),

        )



        responses = []



        start = time.time()



        while (

            time.time() - start

            < timeout

        ):



            try:



                data, addr = sock.recvfrom(

                    4096

                )



                text = data.decode(

                    "utf-8",

                    errors="replace",

                )



                responses.append(

                    {

                        "ip": addr[0],

                        "response": text,

                    }

                )



            except socket.timeout:

                break



        if responses:



            unique_ips = []



            for item in responses:



                ip = item["ip"]



                if ip not in unique_ips:

                    unique_ips.append(ip)



            for ip in unique_ips:



                success(

                    f"Yeelight UDP discovery found: {ip}"

                )



            return responses



        warning(

            "No Yeelight UDP discovery response."

        )



        return []



    except Exception as exc:



        warning(

            f"Yeelight UDP discovery failed: {exc}"

        )



        return []



    finally:



        sock.close()





# ============================================================

# TCP 55443

# ============================================================



def test_tcp_55443(

    ip,

):



    info(

        f"Testing TCP {ip}:{YEELIGHT_PORT}..."

    )



    sock = socket.socket(

        socket.AF_INET,

        socket.SOCK_STREAM,

    )



    try:



        sock.settimeout(5)



        result = sock.connect_ex(

            (

                ip,

                YEELIGHT_PORT,

            )

        )



        if result == 0:



            success(

                f"TCP {YEELIGHT_PORT} is OPEN."

            )



            return True



        warning(

            f"TCP {YEELIGHT_PORT} is CLOSED or unreachable "

            f"(Windows socket error {result})."

        )



        return False



    except Exception as exc:



        warning(

            f"TCP test failed: {exc}"

        )



        return False



    finally:



        sock.close()





# ============================================================

# YEELIGHT JSON PROTOCOL

# ============================================================



def test_yeelight_protocol(
    ip,
):

    info(
        f"Testing Yeelight JSON protocol at "
        f"{ip}:{YEELIGHT_PORT}..."
    )

    command = (
        '{"id":1,"method":"get_prop",'
        '"params":["power","bright","ct","rgb",'
        '"hue","sat","color_mode"]}'
        "\r\n"
    ).encode(
        "utf-8"
    )

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )

    try:

        sock.settimeout(5)

        sock.connect(
            (
                ip,
                YEELIGHT_PORT,
            )
        )

        sock.sendall(
            command
        )

        data = sock.recv(
            4096
        )

        if not data:

            warning(
                "TCP connected, but bulb returned no data."
            )

            return False

        text = data.decode(
            "utf-8",
            errors="replace",
        ).strip()

        try:
            response = json.loads(text)
        except json.JSONDecodeError:
            warning(
                "TCP 55443 responded, but the response was not valid JSON."
            )
            print()
            print("Yeelight response:")
            print(text)
            return False

        if response.get("id") != 1:
            warning(
                "Received JSON from TCP 55443, but the response ID "
                "did not match request ID 1."
            )
            print()
            print("Yeelight response:")
            print(text)
            return False

        if "result" in response:

            success(
                "Yeelight JSON protocol responded successfully."
            )

            print()
            print("Yeelight response:")
            print(text)

            return True

        if "error" in response:

            warning(
                "Yeelight JSON protocol responded with an error."
            )

            print()
            print("Yeelight response:")
            print(text)

            return False

        warning(
            "Received JSON from TCP 55443, but it was not a "
            "recognized Yeelight response."
        )

        print(text)

        return False

    except Exception as exc:

        warning(
            f"Yeelight protocol test failed: {exc}"
        )

        return False

    finally:

        sock.close()


# SAVE INFORMATION

# ============================================================



def save_token(

    token,

):

    if not is_valid_miio_token(token):
        warning(
            "Refusing to write an invalid miIO token. The token file "
            "will not be replaced with a placeholder."
        )
        return False

    try:
        os.makedirs(
            os.path.dirname(TOKEN_FILE),
            exist_ok=True,
        )

        with open(
            TOKEN_FILE,
            "w",
            encoding="utf-8",
        ) as f:
            f.write(token)

        success(
            f"Token saved to {TOKEN_FILE}"
        )
        return True

    except Exception as exc:
        warning(
            f"Could not save token: {exc}"
        )
        return False


def save_recovery_info(
    ip,
    device_id,
    token,
    device_info,
    lan_enabled,
    udp_found,
    tcp_ok,
    protocol_ok,
):

    try:

        token_hash = (
            hashlib.sha256(
                bytes.fromhex(
                    token
                )
            ).hexdigest()
            if token
            else "UNAVAILABLE"
        )

        lan_status = (
            "CONFIRMED WORKING"
            if tcp_ok and protocol_ok
            else "NOT CONFIRMED"
        )

        with open(
            RECOVERY_FILE,
            "w",
            encoding="utf-8",
        ) as f:

            f.write(
                "Yeelight Recovery Information\n"
            )

            f.write(
                "============================\n\n"
            )

            f.write(
                f"Last known IP: {ip}\n"
            )

            f.write(
                f"Device ID: {device_id}\n"
            )

            f.write(
                f"Token SHA-256: {token_hash}\n\n"
            )

            if device_info:

                for key, value in device_info.items():

                    if key == "token":
                        continue

                    f.write(
                        f"{key}: {value}\n"
                    )

            f.write("\n")

            f.write("Yeelight LAN verification\n")
            f.write("-------------------------\n")
            f.write(
                f"LAN Control: {lan_status}\n"
            )
            f.write(
                f"UDP 1982 discovery: "
                f"{'FOUND' if udp_found else 'NOT FOUND'}\n"
            )
            f.write(
                f"TCP 55443: "
                f"{'OPEN' if tcp_ok else 'CLOSED'}\n"
            )
            f.write(
                f"Yeelight protocol: "
                f"{'WORKING' if protocol_ok else 'NOT CONFIRMED'}\n"
            )

            if protocol_ok and not udp_found:
                f.write(
                    "Discovery method: TCP 55443 + Yeelight JSON\n"
                )
            else:
                f.write(
                    "Discovery method: Yeelight LAN diagnostics\n"
                )

            f.write("\n")
            f.write("Interpretation\n")
            f.write("--------------\n")
            f.write(
                "TCP 55443 plus a successful Yeelight JSON response "
                "is the authoritative LAN-control test.\n"
            )
            f.write(
                "miIO authenticated status checks and UDP 1982 "
                "discovery are diagnostic only and are not required "
                "for LAN control.\n"
            )

            f.write("\n")
            f.write(
                "Token itself is stored separately in:\n"
            )
            f.write(
                f"{TOKEN_FILE}\n"
            )

        success(
            f"Recovery information saved to {RECOVERY_FILE}"
        )

    except Exception as exc:

        warning(
            f"Could not save recovery information: {exc}"
        )


# FACTORY RESET / WIFI ONBOARDING

# ============================================================



def configure_home_wifi(

    ip,

    token,

    ssid,

    password,

):



    Yeelight = import_miio()



    if Yeelight is None:

        return False



    step(

        "CONFIGURE BULB FOR HOME WIFI"

    )



    info(

        f"Home SSID: {ssid}"

    )



    info(

        "Wi-Fi password: [hidden]"

    )



    try:



        bulb = Yeelight(

            ip=ip,

            token=token,

        )



        result = bulb.configure_wifi(

            ssid,

            password,

        )



        success(

            f"Bulb accepted Wi-Fi configuration: {result}"

        )



        return True



    except Exception as exc:



        failed(

            "The bulb did not accept the Wi-Fi configuration."

        )



        info(

            f"python-miio reported: {exc}"

        )



        return False





def recover_from_setup_mode(

    interface,

    setup_ssid,

    home_ssid,

    home_password,

):



    step(

        "FACTORY-RESET RECOVERY"

    )



    # --------------------------------------------------------

    # Connect to bulb AP

    # --------------------------------------------------------



    if not connect_wifi(

        setup_ssid

    ):



        return None



    # --------------------------------------------------------

    # Static IP

    # --------------------------------------------------------



    if not configure_temporary_setup_ip(

        interface

    ):



        restore_dhcp(

            interface

        )



        return None



    # --------------------------------------------------------

    # Get setup token

    # --------------------------------------------------------



    step(

        "CONTACT YEELIGHT AT 10.10.1.1"

    )



    setup_identity = miio_hello(

        SETUP_IP,

        timeout=3,

    )



    if setup_identity is None:



        failed(

            "No miIO response from 10.10.1.1."

        )



        restore_dhcp(

            interface

        )



        return None



    success(

        f"Device ID: {setup_identity['device_id']}"

    )



    device_id = setup_identity["device_id"]

    token = setup_identity.get("token")

    if not is_valid_miio_token(token):
        warning(
            "The bulb returned a hidden miIO token instead of a usable "
            "32-character token."
        )
        token = load_saved_token()
        if token:
            success("Using the previously saved valid miIO token.")
        else:
            token = try_cloud_token(device_id=device_id)

    if not is_valid_miio_token(token):
        failed("No valid 32-character miIO token was recovered.")
        warning("The script will NOT save an all-zero/all-FF placeholder as the token.")
        restore_dhcp(interface)
        return None

    success("Valid 32-character miIO token recovered.")



    # --------------------------------------------------------

    # Identify bulb

    # --------------------------------------------------------



    setup_device_info = get_miio_device_info(

        SETUP_IP,

        token,

    )



    # --------------------------------------------------------

    # Attempt LAN Control BEFORE leaving setup mode

    # --------------------------------------------------------



    step(

        "TRY LAN CONTROL WHILE STILL IN SETUP MODE"

    )



    enable_lan_control(

        SETUP_IP,

        token,

    )



    # --------------------------------------------------------

    # Configure home Wi-Fi

    # --------------------------------------------------------



    if not configure_home_wifi(

        SETUP_IP,

        token,

        home_ssid,

        home_password,

    ):



        restore_dhcp(

            interface

        )



        return None



    # Remove password reference.

    home_password = None



    # --------------------------------------------------------

    # Wait for setup AP to disappear

    # --------------------------------------------------------



    step(

        "WAIT FOR BULB TO LEAVE SETUP MODE"

    )



    for _ in range(40):



        current = get_current_wifi_ssid()



        if current != setup_ssid:



            success(

                "PC is no longer connected to the bulb setup network."

            )



            break



        time.sleep(1)



    # --------------------------------------------------------

    # Restore PC

    # --------------------------------------------------------



    restore_dhcp(

        interface

    )



    # --------------------------------------------------------

    # Connect PC to home Wi-Fi

    # --------------------------------------------------------



    if not connect_wifi(

        home_ssid,

        wait_seconds=30,

    ):



        warning(

            "Could not automatically reconnect to home Wi-Fi."

        )



        print()

        input(

            "Connect the PC to home Wi-Fi manually, "

            "then press Enter..."

        )



    time.sleep(5)



    # --------------------------------------------------------

    # Discover bulb

    # --------------------------------------------------------



    local_ip = get_local_ipv4(

        interface

    )



    if not local_ip:



        failed(

            "Could not determine the PC's LAN IP."

        )



        return None



    network = get_ipv4_network(

        interface

    )



    if not network:



        failed(

            "Could not determine the PC's LAN subnet."

        )



        return None



    info(

        f"PC LAN IP: {local_ip}"

    )



    info(

        f"LAN subnet: {network}"

    )



    step(

        "DISCOVER BULB AFTER WIFI CONFIGURATION"

    )



    selected = find_known_device(

        network,

        expected_device_id=device_id,

    )



    if selected is None:



        failed(

            "Could not rediscover the bulb after Wi-Fi configuration."

        )



        return None



    if setup_device_info:

        selected["device_info"] = setup_device_info

    selected["token"] = token

    return selected





# ============================================================

# CURRENT-LAN DISCOVERY

# ============================================================



def discover_existing_bulb(

    interface,

):



    step(

        "FIND BULB ON CURRENT HOME NETWORK"

    )



    local_ip = get_local_ipv4(

        interface

    )



    if not local_ip:



        warning(

            "The PC does not currently have a usable IPv4 address."

        )



        return None



    network = get_ipv4_network(

        interface

    )



    if not network:



        warning(

            "Could not determine the local IPv4 network."

        )



        return None



    success(

        f"PC LAN IP: {local_ip}"

    )



    success(

        f"Scanning network: {network}"

    )



    selected = find_known_device(

        network

    )



    return selected





# ============================================================

# FINAL VERIFICATION

# ============================================================



def verify_lan(
    ip,
    token=None,
):

    step(
        "VERIFY YEELIGHT LAN CONTROL"
    )

    # UDP discovery is optional diagnostic information.
    udp_responses = yeelight_udp_discovery(
        timeout=5
    )

    udp_found = any(
        item["ip"] == ip
        for item in udp_responses
    )

    # TCP 55443 is the Yeelight control channel.
    tcp_ok = test_tcp_55443(
        ip
    )

    # A successful Yeelight JSON response is the authoritative
    # confirmation that LAN control is working.
    protocol_ok = False

    if tcp_ok:

        protocol_ok = test_yeelight_protocol(
            ip
        )

    if tcp_ok and protocol_ok:

        success(
            "LAN Control is CONFIRMED WORKING "
            "by TCP 55443 + Yeelight JSON."
        )

    else:

        warning(
            "LAN Control could not be confirmed by the "
            "authoritative TCP/Yeelight protocol test."
        )

    return (
        udp_found,
        tcp_ok,
        protocol_ok,
    )


# MAIN

# ============================================================



def main():



    banner(

        "YEELIGHT COMPLETE RECOVERY + LAN CONTROL UTILITY"

    )



    print(

        "This version first searches your existing home network."

    )



    print(

        "It does NOT assume the bulb still has yesterday's IP."

    )



    print(

        "If the bulb cannot be found, the script can fall back"

    )



    print(

        "to factory-reset/setup-network recovery."

    )



    print()



    require_admin()



    # --------------------------------------------------------

    # Wi-Fi interface

    # --------------------------------------------------------



    interface = get_wifi_interface()



    if not interface:



        failed(

            "Could not find a Windows Wi-Fi interface."

        )



        input(

            "Press Enter to exit..."

        )



        return



    info(

        f"Wi-Fi interface: {interface}"

    )



    original_ssid = get_current_wifi_ssid()



    if original_ssid:



        info(

            f"Current Wi-Fi: {original_ssid}"

        )



    # --------------------------------------------------------

    # FIRST ATTEMPT:

    # Existing bulb on home LAN

    # --------------------------------------------------------



    selected = discover_existing_bulb(

        interface

    )



    # --------------------------------------------------------

    # SECOND ATTEMPT:

    # Factory-reset setup network

    # --------------------------------------------------------



    if selected is None:



        step(

            "BULB NOT FOUND ON CURRENT HOME NETWORK"

        )



        print(

            "The bulb may be factory-reset or may not currently"

        )



        print(

            "be connected to the same network as this PC."

        )



        print()



        setup_networks = find_setup_networks()



        if not setup_networks:



            failed(

                "No Yeelight setup network was found either."

            )



            print()

            print(

                "Because the bulb was unplugged rather than reset,"

            )

            print(

                "this normally means one of the following:"

            )

            print(

                "  1. The bulb is not powered on."

            )

            print(

                "  2. The bulb is connected to another Wi-Fi network."

            )

            print(

                "  3. The PC is on a different VLAN/subnet."

            )

            print(

                "  4. Windows is blocking local discovery."

            )

            print()

            print(

                "No changes were made to the bulb."

            )



            input(

                "Press Enter to exit..."

            )



            return



        success(

            "Yeelight setup network(s) found:"

        )



        for index, ssid in enumerate(

            setup_networks,

            1,

        ):



            print(

                f"    {index}. {ssid}"

            )



        if len(setup_networks) == 1:



            setup_ssid = setup_networks[0]



        else:



            choice = input(

                "Select setup network number: "

            ).strip()



            try:



                setup_ssid = setup_networks[

                    int(choice) - 1

                ]



            except Exception:



                failed(

                    "Invalid selection."

                )



                return



        home_ssid = input(

            "Home Wi-Fi SSID for the bulb: "

        ).strip()



        if not home_ssid:



            failed(

                "No home Wi-Fi SSID supplied."

            )



            return



        home_password = getpass.getpass(

            "Home Wi-Fi password: "

        )



        selected = recover_from_setup_mode(

            interface,

            setup_ssid,

            home_ssid,

            home_password,

        )



        home_password = None



        if selected is None:



            failed(

                "Recovery failed."

            )



            input(

                "Press Enter to exit..."

            )



            return



    # --------------------------------------------------------

    # We now know the bulb's CURRENT IP
    # --------------------------------------------------------

    bulb_ip = selected["ip"]
    device_id = selected["device_id"]
    bulb_token = selected["token"]

    step(
        "BULB FOUND"
    )

    success(
        f"Current bulb IP: {bulb_ip}"
    )

    success(
        f"Device ID: {device_id}"
    )

    success(
        "Current token recovered."
    )

    # Do not make authenticated miIO status or LAN-enable calls
    # after the bulb has joined the home network. Those calls can
    # time out even while Yeelight TCP control is fully operational.
    #
    # The setup-mode recovery path above still uses miIO where it
    # is needed for token retrieval, LAN-control enablement, and
    # Wi-Fi provisioning.

    device_info = selected.get("device_info")

    # --------------------------------------------------------
    # Verify Yeelight LAN control
    # --------------------------------------------------------

    udp_found, tcp_ok, protocol_ok = verify_lan(
        bulb_ip,
        bulb_token,
    )

    # TCP 55443 + successful Yeelight JSON is authoritative.
    lan_enabled = tcp_ok and protocol_ok

    # --------------------------------------------------------
    # Save recovery information
    # --------------------------------------------------------

    step(
        "SAVE RECOVERY INFORMATION"
    )

    save_token(
        bulb_token
    )

    save_recovery_info(
        bulb_ip,
        device_id,
        bulb_token,
        device_info,
        lan_enabled,
        udp_found,
        tcp_ok,
        protocol_ok,
    )

    # --------------------------------------------------------
    # Final
    # --------------------------------------------------------

    banner(
        "YEELIGHT RECOVERY COMPLETE"
    )

    print(
        f"Current bulb IP:     {bulb_ip}"
    )

    print(
        f"Device ID:           {device_id}"
    )

    print(
        "Current token:       RECOVERED"
    )

    print()

    print(
        "LAN Control:         "
        + (
            "CONFIRMED WORKING"
            if tcp_ok and protocol_ok
            else "NOT CONFIRMED"
        )
    )

    print(
        "Yeelight UDP:        "
        + (
            "FOUND"
            if udp_found
            else "NOT FOUND"
        )
    )

    print(
        "TCP 55443:           "
        + (
            "OPEN"
            if tcp_ok
            else "CLOSED"
        )
    )

    print(
        "Yeelight protocol:   "
        + (
            "WORKING"
            if protocol_ok
            else "NOT CONFIRMED"
        )
    )

    print()

    print(
        f"Token file:          {TOKEN_FILE}"
    )

    print(
        f"Recovery file:       {RECOVERY_FILE}"
    )

    print()

    if tcp_ok and protocol_ok:

        success(
            "LAN CONTROL IS WORKING."
        )

        print()

        print(
            "Your Stock Orb should now be able to communicate"
        )

        print(
            "with the bulb directly over Yeelight TCP 55443."
        )

        if not udp_found:

            print()

            info(
                "UDP 1982 discovery was not required because "
                "the bulb responded successfully on TCP 55443."
            )

    elif tcp_ok:

        warning(
            "TCP 55443 is open, but the Yeelight protocol "
            "test did not fully confirm operation."
        )

    else:

        warning(
            "LAN Control could not be confirmed."
        )

        print()

        print(
            "No post-provisioning miIO enable attempts will be made."
        )

        print(
            "If the bulb was just provisioned, check its IP and "
            "home-network connectivity before factory-resetting it."
        )

    print()

    input(
        "Press Enter to exit..."
    )


# ENTRY POINT

# ============================================================



if __name__ == "__main__":



    try:



        main()



    except KeyboardInterrupt:



        print()



        warning(

            "Operation cancelled by user."

        )



    except Exception as exc:



        print()



        failed(

            "Unexpected error."

        )



        print()



        print(

            f"{type(exc).__name__}: {exc}"

        )



        print()



        input(

            "Press Enter to exit..."

        )