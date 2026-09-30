"""Explicitly simulated network adapter for the localhost-only design preview."""
import time
import uuid
from .network import validate_network


class PreviewNetwork:
    def __init__(self):
        self.pending = None
        self.items = [
            {'interface': 'eth0', 'kind': 'ethernet', 'state': 'connected', 'connection': 'Example wired network', 'address': '192.168.1.50/24', 'gateway': '192.168.1.1', 'dns': '192.168.1.1'},
            {'interface': 'wlan0', 'kind': 'wifi', 'state': 'sample interface', 'connection': '', 'address': '', 'gateway': '', 'dns': ''},
        ]

    def status(self):
        if self.pending and time.time() >= self.pending['deadline']:
            self.pending = None
        return {'available': True, 'devices': self.items, 'ethernet_connected': True, 'pending': self.pending,
                'message': 'Preview only: interfaces and Wi-Fi networks below are examples. Applying settings does not change your computer.'}

    def scan(self):
        return [{'ssid': 'Example home Wi-Fi', 'signal': 92, 'security': 'WPA2', 'interface': 'wlan0'},
                {'ssid': 'Example workshop', 'signal': 68, 'security': 'WPA3', 'interface': 'wlan0'}]

    def apply(self, body):
        settings = validate_network(body, self.items)
        self.pending = {'id': str(uuid.uuid4()), 'deadline': time.time() + 120,
                        'interface': settings['interface'], 'phase': 'awaiting_confirmation'}
        return {**self.pending, 'message': 'Preview: simulated network change ready for confirmation. No real settings changed.'}

    def confirm(self, identity):
        if not self.pending or self.pending['id'] != identity:
            raise ValueError('No pending preview change.')
        self.pending = None
        return {'message': 'Preview confirmed. Your computer network is unchanged.'}

    def rollback(self, identity):
        if not self.pending or self.pending['id'] != identity:
            raise ValueError('No pending preview change.')
        self.pending = None
        return {'message': 'Preview reverted. Your computer network is unchanged.'}
