"""
Simple HTTP server for serving Foliate-js files locally

This solves the ES module CORS issue with file:// URLs
"""

import http.server
import socketserver
import threading
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that doesn't log every request"""

    def log_message(self, format, *args):
        # Only log errors
        if args[1][0] != '2' and args[1][0] != '3':
            logger.warning(format % args)

    def end_headers(self):
        # Add CORS headers to allow ES modules
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()


class FoliateHTTPServer:
    """HTTP server manager for Foliate-js"""

    def __init__(self, port=8765):
        self.port = port
        self.httpd = None
        self.thread = None
        self.base_dir = None

    def start(self, directory=None):
        """
        Start the HTTP server

        Args:
            directory: Directory to serve (default: current working directory)

        Returns:
            True if started successfully, False otherwise
        """
        if self.httpd:
            logger.warning("Server already running")
            return True

        # Save current directory
        original_dir = os.getcwd()

        try:
            # Change to serving directory
            if directory:
                os.chdir(directory)
                self.base_dir = directory
            else:
                self.base_dir = os.getcwd()

            # Create server
            self.httpd = socketserver.TCPServer(
                ("localhost", self.port),
                QuietHTTPRequestHandler,
                bind_and_activate=False
            )
            self.httpd.allow_reuse_address = True
            self.httpd.server_bind()
            self.httpd.server_activate()

            # Start server thread
            self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.thread.start()

            logger.info(f"HTTP server started on http://localhost:{self.port}")
            logger.info(f"Serving directory: {self.base_dir}")

            # Restore original directory
            os.chdir(original_dir)

            return True

        except OSError as e:
            logger.error(f"Failed to start HTTP server on port {self.port}: {e}")
            # Restore original directory
            os.chdir(original_dir)
            return False

    def stop(self):
        """Stop the HTTP server"""
        if self.httpd:
            logger.info("Shutting down HTTP server...")
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
            self.thread = None

    def get_url(self, path=""):
        """
        Get URL for a path on the server

        Args:
            path: Relative path from base directory

        Returns:
            Full HTTP URL
        """
        if path.startswith('/'):
            path = path[1:]
        return f"http://localhost:{self.port}/{path}"

    def is_running(self):
        """Check if server is running"""
        return self.httpd is not None
