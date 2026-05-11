#!/usr/bin/env python3
"""
PLC Toolkit - Export Tool - Module
This script reads tag data from the local database and generates reports.
"""

import os
import json
from datetime import datetime
import xml.etree.ElementTree as ET
import xml.dom.minidom

try:
    import openpyxl
except ImportError:
    openpyxl = None  # Handled gracefully

class TagExporter:
    def __init__(self, db_conn, plc_id):
        self.conn = db_conn
        self.plc_id = plc_id
        self.plc_info = {}
        # The data from the DB is already parsed and sanitized.
        self.parsed_tags = self._load_data_from_db()

    def _load_data_from_db(self):
        """Loads PLC info and the parsed tag data from the SQLite database."""
        cursor = self.conn.cursor()
        self.plc_info = cursor.execute('SELECT * FROM plcs WHERE id = ?', (self.plc_id,)).fetchone()
        
        tags_json = cursor.execute('SELECT tags_json FROM tag_data WHERE plc_id = ?', (self.plc_id,)).fetchone()[0]
        # The stored data is a clean, nested dictionary.
        return json.loads(tags_json)

    def generate_excel_flat(self, output_file):
        """Generates a clean, flat Excel report."""
        rows = []
        def flatten(parent, prefix, info):
            if isinstance(info, dict) and 'members' in info:
                for name, sub_info in sorted(info['members'].items()):
                    flatten(parent, f"{prefix}.{name}", sub_info)
            else:
                rows.append(['', f"{parent}{prefix}", str(info)])

        for tag_name, tag_info in sorted(self.parsed_tags.items()):
            if isinstance(tag_info, dict) and 'members' in tag_info:
                rows.append([tag_name, '', tag_info.get('_data_type_', 'UDT')])
                for name, member_info in sorted(tag_info['members'].items()):
                    flatten(tag_name, f".{name}", member_info)
            else:
                rows.append([tag_name, tag_name, str(tag_info)])

        print(f"\nGenerating Excel report with {len(rows)} rows...")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "PLC Tags"
        ws.append(['Tag', 'Full Path', 'Data Type'])
        for row in rows:
            ws.append(row)
        ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            length = max(len(str(cell.value or '')) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = (length + 2) if length < 80 else 80
        wb.save(output_file)
        print(f"Excel report saved to: {os.path.abspath(output_file)}")

    def save_json(self, json_file):
        """Saves the parsed, nested tag data to a JSON file."""
        try:
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(self.parsed_tags, f, indent=2, default=str)
            print(f"JSON report saved to: {os.path.abspath(json_file)}")
        except Exception as e:
            print(f"Failed to save JSON: {str(e)}")

    def save_xml(self, xml_file):
        """Saves the parsed, nested tag data to an XML file."""
        try:
            root = ET.Element('PLCTagScan')
            def build_xml_node(parent, name, info):
                if isinstance(info, dict) and 'members' in info:
                    node = ET.SubElement(parent, 'Tag', name=name, dataType=info.get('_data_type_', 'STRUCT'))
                    for member_name, member_info in info['members'].items():
                        build_xml_node(node, member_name, member_info)
                else:
                    ET.SubElement(parent, 'Member', name=name, dataType=str(info))
            tags_root = ET.SubElement(root, 'Tags')
            for name, info in sorted(self.parsed_tags.items()):
                build_xml_node(tags_root, name, info)
            xml_string = ET.tostring(root, 'utf-8')
            dom = xml.dom.minidom.parseString(xml_string)
            with open(xml_file, 'w', encoding='utf-8') as f:
                f.write(dom.toprettyxml(indent="  "))
            print(f"XML report saved to: {os.path.abspath(xml_file)}")
        except Exception as e:
            print(f"Failed to save XML: {str(e)}")


def run_exporter(db_connection, plc_id):
    """
    Main entry point for the export tool.
    """
    print("\n--- Tag Export Tool ---")
    
    exporter = TagExporter(db_connection, plc_id)

    output_folder = "plc_scans"
    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    
    plc_ip = exporter.plc_info[1]
    ip_sanitized = plc_ip.replace('.', '_')
    base_filepath = os.path.join(output_folder, f"{timestamp}_{ip_sanitized}_tags")

    print("\nConfiguration:")
    print(f"  PLC IP:       {plc_ip}")
    print(f"  Output Files: {base_filepath}.(xlsx, json, xml)")
    
    proceed = input("\nProceed with export? [Y/n]: ").strip().lower()
    if proceed == 'n':
        print("Cancelled.")
        return

    if openpyxl:
        exporter.generate_excel_flat(f"{base_filepath}.xlsx")
    else:
        print("\nSkipping Excel report generation ('openpyxl' not found).")
    
    exporter.save_json(f"{base_filepath}_full.json")
    exporter.save_xml(f"{base_filepath}_full.xml")

    print("\n✓ Export complete!")

