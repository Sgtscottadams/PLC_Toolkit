"""Help dialog — MVP troubleshooting and glossary."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

_HELP_HTML = """
<h2>PLC Toolkit — Help</h2>
<p><b>READ-ONLY:</b> v2.0 does not write to the PLC. You can browse, monitor,
and export tag values only.</p>

<h3>Can't connect</h3>
<ul>
<li>Verify the IP address and processor slot (usually <b>0</b> for CompactLogix/ControlLogix).</li>
<li>Confirm the PLC is powered and reachable from this PC (ping the IP).</li>
<li>Check VPN or firewall rules — EtherNet/IP uses <b>TCP and UDP port 44818</b>.</li>
<li>On radio-linked sites, allow extra time; increase connection timeout in Settings.</li>
</ul>

<h3>Test connection failed</h3>
<ul>
<li><b>Timeout</b> — PLC unreachable, wrong subnet, or radio latency. Retry with a longer timeout.</li>
<li><b>Wrong slot</b> — Most CompactLogix/CompactLogix use slot 0. ControlLogix chassis modules may differ.</li>
<li><b>CIP path</b> (advanced) — Leave blank unless your integrator specified a backplane path.</li>
</ul>

<h3>Subnet scan found nothing</h3>
<ul>
<li>Use CIDR notation: <code>172.17.117.0/24</code> (not just the broadcast address).</li>
<li>Your PC must be on the same network as the PLCs.</li>
<li>Broadcast may be blocked — the scanner also tries direct TCP probes; wait for the full progress bar.</li>
<li>If you know an IP, use <b>+ Connect to a new PLC</b> instead of scanning.</li>
</ul>

<h3>Browse empty or discovery slow</h3>
<ul>
<li>After connecting, tag discovery runs in the background — watch the blue banner on the Browse tab.</li>
<li>Large programs with many UDTs can take several minutes on first connect.</li>
<li>Use <b>Re-discover</b> only when you need a fresh tag list from the PLC.</li>
</ul>

<h3>Glossary</h3>
<dl>
<dt>UDT</dt><dd>User-defined data type — a structured tag with members (like a struct).</dd>
<dt>BOOL</dt><dd>Boolean tag (0/1, TRUE/FALSE).</dd>
<dt>REAL</dt><dd>32-bit floating-point value.</dd>
<dt>DINT</dt><dd>32-bit signed integer.</dd>
<dt>CIP</dt><dd>Common Industrial Protocol — the messaging layer over EtherNet/IP.</dd>
<dt>EtherNet/IP</dt><dd>Industrial Ethernet protocol used by Allen-Bradley Logix PLCs (port 44818).</dd>
<dt>Slot</dt><dd>Processor slot number in the chassis (0 for most standalone controllers).</dd>
<dt>Quality Good / Bad</dt><dd>Whether the last read succeeded (Good) or failed (Bad).</dd>
</dl>
"""


class HelpDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Help")
        self.resize(560, 480)

        label = QLabel(_HELP_HTML)
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)
        label.setOpenExternalLinks(False)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.addWidget(label)
        scroll.setWidget(body)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        outer = QVBoxLayout(self)
        outer.addWidget(scroll)
        outer.addWidget(buttons)
