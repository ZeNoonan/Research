#!/usr/bin/env python3
"""
Simple HTTP Server for Kelly Criterion Web App
===============================================
Serves the web app so you can access it from your phone or other devices
on the same network.

Usage:
    python3 serve.py [port]

Default port: 8000

After starting, access from any device on your network at:
    http://YOUR_IP_ADDRESS:8000/kelly_game.html

Your local IP addresses will be displayed when the server starts.
"""

import http.server
import socketserver
import socket
import sys
import os
from pathlib import Path


def get_local_ips():
    """Get all local IP addresses."""
    ips = []

    # Get hostname-based IP
    try:
        hostname = socket.gethostname()
        host_ip = socket.gethostbyname(hostname)
        if host_ip and host_ip != '127.0.0.1':
            ips.append(host_ip)
    except:
        pass

    # Get all network interfaces
    try:
        import netifaces
        for interface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr['addr']
                    if ip != '127.0.0.1' and not ip.startswith('169.254'):
                        ips.append(ip)
    except ImportError:
        # netifaces not available, use socket method
        try:
            # Connect to external server to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and ip not in ips:
                ips.append(ip)
        except:
            pass

    return list(set(ips))  # Remove duplicates


def main():
    # Get port from command line or use default
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port number: {sys.argv[1]}")
            print("Using default port 8000")

    # Change to script directory
    os.chdir(Path(__file__).parent)

    # Check if kelly_game.html exists
    if not Path('kelly_game.html').exists():
        print("Error: kelly_game.html not found in current directory!")
        print(f"Current directory: {os.getcwd()}")
        sys.exit(1)

    # Create server
    Handler = http.server.SimpleHTTPRequestHandler

    try:
        with socketserver.TCPServer(("", port), Handler) as httpd:
            print("=" * 70)
            print("🪙 Kelly Criterion Web App Server")
            print("=" * 70)
            print(f"\nServer running on port {port}")
            print("\nAccess the web app from your device at:\n")

            # Get and display local IPs
            ips = get_local_ips()

            if ips:
                print("📱 From your phone or other device:")
                for ip in ips:
                    print(f"   http://{ip}:{port}/kelly_game.html")
            else:
                print("   Unable to determine local IP address")
                print("   Try: http://localhost:8000/kelly_game.html")

            print("\n💻 From this computer:")
            print(f"   http://localhost:{port}/kelly_game.html")

            print("\n" + "=" * 70)
            print("Press Ctrl+C to stop the server")
            print("=" * 70 + "\n")

            # Serve forever
            httpd.serve_forever()

    except PermissionError:
        print(f"\nError: Permission denied for port {port}")
        print("Try using a port number above 1024, e.g.:")
        print(f"    python3 serve.py 8080")
        sys.exit(1)
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"\nError: Port {port} is already in use")
            print("Try a different port, e.g.:")
            print(f"    python3 serve.py {port + 1}")
        else:
            print(f"\nError: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped. Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
