# Yeelight Complete Recovery + LAN Control Utility

This project is a Windows Python utility for discovering Yeelight smart bulbs, recovering their network connections, retrieving device information, and enabling or verifying LAN control without relying on the proprietary Yeelight app.

The utility was developed to future-proof access to older Yeelight bulbs in case the Yeelight Classic app is discontinued, potentially removing the usual way to discover these devices and enable LAN control.

This project was primarily developed to support [The Stock Orb](https://github.com/NoahAdamSperling/Stock_Orb), a Python script that uses a Yeelight smart bulb as a real-time visual indicator of stock market performance relative to the previous day's closing price.

## What It Does

The utility can:

1. Search the current local network for an existing Yeelight bulb and identify its IP address.
2. Retrieve the bulb's miIO device ID and, when available, its usable miIO token.
3. Identify device information such as model, firmware, hardware, and MAC address when the bulb provides it.
4. Check or attempt to enable Yeelight LAN/developer mode while the bulb is reachable over its setup network.
5. If the bulb is in factory-reset/setup mode, find its setup Wi-Fi network, connect the PC to it, configure the temporary network settings needed to contact the bulb, and provision the bulb with the user's home Wi-Fi credentials.
6. Restore the PC's Wi-Fi adapter to DHCP and reconnect to the home network after setup-mode recovery.
7. Test Yeelight UDP discovery as a diagnostic, check TCP port `55443`, and send a Yeelight JSON request to verify actual LAN control.
8. Save recovery details and a valid recovered token locally on the Windows desktop.

## Requirements

- Windows 10 or Windows 11
- Python 3.10 or newer
- A Wi-Fi adapter that can connect to the Yeelight setup network
- Administrator privileges for the terminal or editor running the script

### Python packages

Install the main dependency from PowerShell or Command Prompt:

```powershell
python -m pip install python-miio==0.5.12
```

The script can optionally attempt token recovery through Xiaomi Cloud if the bulb's miIO handshake does not provide a usable token. For that optional feature, install `micloud`:

```powershell
python -m pip install micloud
```

If Windows has multiple Python installations, use the same Python executable to install packages that you use to run the script. For example:

```powershell
py -3 -m pip install python-miio==0.5.12
py -3 -m pip install micloud
```

`micloud` is only needed for the optional Xiaomi Cloud token-recovery attempt. The core recovery and LAN diagnostic workflow uses `python-miio`.

## How to Run

1. Save `yeelight_recovery.py` to a local folder.
2. Open **PowerShell as Administrator** or launch **VS Code as Administrator** and open the script there.
3. Change to the folder containing the script, if needed.
4. Run it:

   ```powershell
   python .\yeelight_recovery.py
   ```

5. Follow the prompts. If the script needs to provision a bulb in setup mode, it will ask for the home Wi-Fi network name and password. If Xiaomi Cloud token recovery is needed and `micloud` is installed, it may also ask for Xiaomi/Mi Home login details.

The script checks for administrator privileges because factory-reset recovery can change the Windows Wi-Fi adapter's IPv4 configuration and reconnect it to different Wi-Fi networks. Run it only on a PC and network you are authorized to administer.

## How It Works

### 1. Search the current network first

The utility starts by examining the current Windows Wi-Fi connection and scanning the local network for miIO devices. This avoids assuming the bulb still has a previously known IP address.

### 2. Fall back to the bulb's setup network

If the bulb cannot be found on the current network, the utility scans for setup-network names beginning with common prefixes such as `yeelink-light-` and `yeelight-`. If a matching network is found, the script can connect to it and configure the PC's Wi-Fi adapter with the temporary address `10.10.1.2/24` to contact the bulb at `10.10.1.1`.

The script then attempts to identify the bulb, enable LAN control while it is still reachable in setup mode, and configure it to join the supplied home Wi-Fi network. It subsequently attempts to restore the PC adapter to DHCP and reconnect to the home network before searching for the bulb again.

### 3. Verify LAN control using the actual control protocol

The utility checks several things, but they do not all have the same significance:

- **TCP port `55443` is open:** The bulb is accepting a TCP connection on the Yeelight LAN control port.
- **Yeelight JSON request succeeds:** The bulb responds to a valid `get_prop` request. This is the utility's authoritative confirmation that LAN control is working.
- **UDP port `1982` discovery:** This is an optional diagnostic. A missing UDP discovery response does not, by itself, mean LAN control is broken.

A successful TCP connection plus a valid Yeelight JSON response is the key result. It confirms that software such as Stock Orb can communicate with the bulb directly over the local network, even if UDP discovery or authenticated miIO status checks do not work.

## Files Created

The utility saves its output to the current Windows user's desktop:

- `yeelight_token.txt` contains the recovered miIO token, if a valid token is available.
- `yeelight_recovery_info.txt` contains the last known IP address, device ID, token hash, available device details, and LAN verification results.

The script rejects all-zero and all-`f` token placeholders rather than saving them as valid tokens. A token hash in the recovery report is not the token itself and cannot be used in its place.

## Important Notes and Troubleshooting

- **Run as Administrator.** This is especially important for the factory-reset path, which changes Wi-Fi adapter settings.
- **Stay nearby and keep the bulb powered on.** The PC must be able to see the bulb's setup network during factory-reset recovery.
- **The PC may temporarily disconnect from the home network.** During setup-mode recovery, the script connects to the bulb's Wi-Fi network and temporarily changes the adapter's IPv4 configuration. It attempts to restore DHCP and reconnect afterward. If that does not happen automatically, reconnect to the home Wi-Fi manually and check that the adapter is set to obtain an IP address automatically.
- **Do not factory-reset a bulb just because an authenticated miIO request times out.** Some bulbs may still respond correctly to Yeelight LAN commands even when authenticated miIO status calls time out.
- **Do not treat missing UDP discovery as a failure on its own.** Check the TCP and Yeelight JSON results first.
- **If the bulb is not found,** confirm that the PC and bulb are on the same local network, the bulb is powered on, and Windows is connected to the expected Wi-Fi adapter/network. Some routers isolate wireless clients or separate devices across VLANs.
- **If Python reports a missing package,** install it using the same Python interpreter that runs the script. The script prints a suggested install command if `python-miio` is missing.
- **If token recovery through Xiaomi Cloud fails,** the bulb may not be associated with the account/region used, the optional `micloud` dependency may be missing, or the cloud API may not return a matching device. LAN control can still be verified separately through TCP `55443` and the Yeelight JSON protocol.

## Security Notes

- The Wi-Fi password is requested at runtime and is not intentionally printed to the console. Review the script before relying on this behavior.
- Xiaomi/Mi Home credentials, if requested for optional cloud token recovery, are entered at runtime. Review the script to confirm how credentials and errors are handled before using it with your account.
- The recovered miIO token is a credential. Keep `yeelight_token.txt` private and **never commit it to GitHub**.
- Do not commit `yeelight_recovery_info.txt` either. Although it stores a token hash rather than the raw token, it can contain device identifiers, network details, and other information you may not want to publish.
- Review the script and its output before sharing logs or screenshots. Replace personal network names, IP addresses, device IDs, and MAC addresses with dummy values.

A `.gitignore` for this project should include at least:

```gitignore
# Local Yeelight credentials and device details
yeelight_token.txt
yeelight_recovery_info.txt

# Python artifacts
__pycache__/
*.py[cod]

# Local environment and configuration
.env
.env.*
!.env.example
*.local
```

## Limitations

- This utility is designed for Windows and uses Windows networking commands such as `netsh`, `ipconfig`, and PowerShell.
- Recovery depends on the bulb exposing a compatible setup network and accepting the provisioning commands used by `python-miio`.
- Network isolation, firewall rules, router configuration, bulb firmware, and Xiaomi Cloud behavior can affect discovery or recovery.
- A recovered miIO token is useful for authenticated miIO operations, but ordinary Yeelight LAN control is verified separately through TCP `55443` and the Yeelight JSON protocol.

## Related Project

[The Stock Orb](https://github.com/NoahAdamSperling/Stock_Orb) uses a Yeelight smart bulb as a real-time visual indicator for market data. This recovery utility can help get a compatible bulb back onto the local network and confirm that its Yeelight LAN control channel is responding. This is especially relevant if the official Yeelight Classic app becomes unavailable.

## Glossary

- **LAN (Local Area Network) control:** A feature that allows a device to be controlled over a local network. It does not necessarily prevent the device from using cloud services for other features.
- **miIO device ID (`did`):** A numeric identifier assigned to a Xiaomi/Mi IoT device.
- **MAC (Media Access Control ) address:** A 48-bit hardware address, conventionally represented by 12 hexadecimal digits, used to identify a network interface on a local network.
- **DHCP (Dynamic Host Configuration Protocol):** A network protocol that automatically assigns IP addresses and other network settings to devices.
- **UDP (User Datagram Protocol):** A connectionless transport protocol that sends data packets without establishing a connection first.
- **TCP (Transmission Control Protocol):** A transport protocol that establishes a connection between endpoints to deliver data reliably and in order. A TCP port is a numbered endpoint used to direct traffic to the appropriate service on a device.
- **JSON (JavaScript Object Notation):** A lightweight text format for representing structured data and exchanging it between programs.

## Disclaimer

This is an independent community utility provided as-is, without any warranty. Use it at your own risk. Network configuration changes can temporarily interrupt connectivity. Always review the code before running it with administrator privileges, and only use it on devices and networks you are authorized to manage.
