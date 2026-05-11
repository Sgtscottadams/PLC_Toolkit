#!/usr/bin/env python3
"""
PLC Toolkit - Consolidated Version
A unified tool for Allen-Bradley PLC tag discovery, export, and monitoring.
Combines all functionality into a single, well-organized class structure.
"""

import os
import sys
import json
import sqlite3
import threading
import time
import xml.etree.ElementTree as ET
import xml.dom.minidom
from datetime import datetime
from collections import deque
from pathlib import Path
from pycomm3 import LogixDriver

try:
    import openpyxl
except ImportError:
    # Handled gracefully: If openpyxl is not installed, Excel export will be skipped
    openpyxl = None

# Configuration Constants
DATABASE_FILE = 'plc_data.db'
OUTPUT_FOLDER = 'plc_scans'
MONITOR_REFRESH_SECONDS = 5
MONITOR_HISTORY_SIZE = 10

# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def clear_screen():
    """Clears the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def animated_task(target_func, *args, **kwargs):
    """Runs a function in a separate thread while showing a working animation."""
    message = kwargs.pop('message', 'Working')
    sys.stdout.write(message + " ")
    
    done_event = threading.Event()
    result = {'value': None, 'error': None}
    
    def task_wrapper():
        try:
            result['value'] = target_func(*args, **kwargs)
        except Exception as e:
            result['error'] = e
        done_event.set()

    thread = threading.Thread(target=task_wrapper)
    thread.start()

    while not done_event.is_set():
        sys.stdout.write('.')
        sys.stdout.flush()
        time.sleep(0.5)
    
    thread.join()
    print(" DONE")
    
    if result['error']:
        raise result['error']
    return result['value']

# ==============================================================================
# DATABASE MANAGER CLASS
# ==============================================================================

class DatabaseManager:
    """Handles all SQLite database operations."""
    
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = sqlite3.connect(db_file)
        self.create_tables()

    def create_tables(self):
        """Creates the necessary database tables if they don't exist."""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS plcs (
                id INTEGER PRIMARY KEY,
                ip_address TEXT NOT NULL,
                slot INTEGER NOT NULL,
                name TEXT,
                revision TEXT,
                last_scan TEXT,
                UNIQUE(ip_address, slot)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tag_data (
                plc_id INTEGER PRIMARY KEY,
                tags_json TEXT,
                FOREIGN KEY (plc_id) REFERENCES plcs (id)
            )
        ''')
        self.conn.commit()

    def update_plc_data(self, ip, slot, info, tags):
        """Inserts or updates PLC info and its associated tag data."""
        cursor = self.conn.cursor()
        rev = info.get('revision', {})
        rev_str = f"{rev.get('major', '?')}.{rev.get('minor', '?')}"
        scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute('''
            INSERT INTO plcs (ip_address, slot, name, revision, last_scan)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ip_address, slot) DO UPDATE SET
                name=excluded.name,
                revision=excluded.revision,
                last_scan=excluded.last_scan
        ''', (ip, slot, info.get('plc_name'), rev_str, scan_time))
        
        plc_id = cursor.execute(
            'SELECT id FROM plcs WHERE ip_address = ? AND slot = ?', 
            (ip, slot)
        ).fetchone()[0]
        
        tags_json = json.dumps(tags)
        cursor.execute('''
            INSERT INTO tag_data (plc_id, tags_json)
            VALUES (?, ?)
            ON CONFLICT(plc_id) DO UPDATE SET
                tags_json=excluded.tags_json
        ''', (plc_id, tags_json))
        
        self.conn.commit()
        return plc_id
    
    def get_plc_info(self, plc_id):
        """Retrieves PLC information from the database."""
        cursor = self.conn.cursor()
        result = cursor.execute(
            'SELECT * FROM plcs WHERE id = ?', 
            (plc_id,)
        ).fetchone()
        return result
    
    def get_tag_data(self, plc_id):
        """Retrieves tag data from the database."""
        cursor = self.conn.cursor()
        result = cursor.execute(
            'SELECT tags_json FROM tag_data WHERE plc_id = ?', 
            (plc_id,)
        ).fetchone()
        return json.loads(result[0]) if result else {}

    def close(self):
        """Closes the database connection."""
        self.conn.close()

# ==============================================================================
# MAIN PLC TOOLKIT CLASS
# ==============================================================================

class PLCToolkit:
    """Unified toolkit for Allen-Bradley PLC operations."""
    
    def __init__(self):
        self.db = DatabaseManager(DATABASE_FILE)
        self.plc = None
        self.plc_info = {}
        self.plc_id = None
        self.ip = None
        self.slot = 0
        self.tags = {}
        
        # For monitoring
        self.stop_monitoring = threading.Event()
        
        # Ensure output folder exists
        Path(OUTPUT_FOLDER).mkdir(exist_ok=True)
    
    # ==========================================================================
    # CONNECTION & DISCOVERY METHODS
    # ==========================================================================
    
    def connect(self, ip, slot=0):
        """Establishes connection to the PLC."""
        self.ip = ip
        self.slot = slot
        
        try:
            print(f"Connecting to PLC at {ip}, slot {slot}...")
            self.plc = LogixDriver(ip, slot=slot, timeout=10, init_tags=False)
            self.plc.open()
            
            self.plc_info = self.plc.get_plc_info()
            print(f"Connected to: {self.plc_info.get('plc_name', 'Unknown PLC')}")
            
            rev = self.plc_info.get('revision', {})
            if isinstance(rev, dict):
                print(f"Revision: {rev.get('major', '?')}.{rev.get('minor', '?')}")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Connection failed: {str(e)}")
            if self.plc and self.plc.connected:
                self.plc.close()
                self.plc = None
            return False
    
    def disconnect(self):
        """Safely disconnects from the PLC."""
        if self.plc and self.plc.connected:
            self.plc.close()
            print("Disconnected from PLC.")
        self.plc = None
    
    def discover_tags(self):
        """Discovers all tags from the connected PLC."""
        if not self.plc or not self.plc.connected:
            raise Exception("Not connected to PLC")
        
        initial_tag_list = []
        
        # Get controller-scoped tags
        controller_tags = self.plc.get_tag_list()
        if controller_tags:
            initial_tag_list.extend(controller_tags)
        
        # Get program-scoped tags
        try:
            programs_tag = self.plc.read('PROGRAM')
            if programs_tag and programs_tag.value:
                for prog_name in programs_tag.value:
                    try:
                        program_tags = self.plc.get_tag_list(program=prog_name)
                        if program_tags:
                            for tag in program_tags:
                                tag['tag_name'] = f"Program:{prog_name}.{tag['tag_name']}"
                            initial_tag_list.extend(program_tags)
                    except Exception:
                        pass
        except Exception:
            pass
        
        # Process all tags
        parsed_tags = {}
        total = len(initial_tag_list)
        sys.stdout.write(f"\rReading {total} Tags ")
        
        for i, summary in enumerate(initial_tag_list):
            name = summary.get('tag_name')
            if not name or name.startswith('__') or name.startswith('System:'):
                continue
            
            try:
                full_def = self.plc.get_tag_info(name)
                parsed_tags[name] = self._parse_structure_def(full_def)
            except Exception:
                dt = summary.get('data_type', 'UNKNOWN')
                if hasattr(dt, 'name'):
                    parsed_tags[name] = dt.name
                else:
                    parsed_tags[name] = str(dt)
            
            if (i + 1) % 10 == 0 or i + 1 == total:
                sys.stdout.write('.')
                sys.stdout.flush()
        
        self.tags = parsed_tags
        return parsed_tags
    
    def _parse_structure_def(self, tag_def):
        """Recursively parses a tag definition into JSON-serializable format."""
        def get_type_name(data_type_value):
            if isinstance(data_type_value, dict):
                return data_type_value.get('name', 'STRUCT')
            if hasattr(data_type_value, 'name'):
                return data_type_value.name
            return str(data_type_value)
        
        members_source = None
        if 'data_type' in tag_def and isinstance(tag_def['data_type'], dict):
            members_source = tag_def['data_type'].get('internal_tags')
        
        if not members_source:
            return get_type_name(tag_def.get('data_type', 'Unknown'))
        
        structure = {
            '_data_type_': get_type_name(tag_def.get('data_type', 'UDT')),
            'members': {}
        }
        
        for member_name, member_data in members_source.items():
            if not member_name.startswith('__'):
                structure['members'][member_name] = self._parse_structure_def(member_data)
        
        return structure
    
    # ==========================================================================
    # EXPORT METHODS
    # ==========================================================================
    
    def export_all(self, base_filename=None):
        """Exports tag data to all supported formats."""
        if not self.tags and self.plc_id:
            self.tags = self.db.get_tag_data(self.plc_id)
        
        if not self.tags:
            print("[ERROR] No tag data available to export.")
            return False
        
        if not base_filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            ip_safe = self.ip.replace('.', '_') if self.ip else 'unknown'
            base_filename = f"{timestamp}_{ip_safe}_tags"
        
        base_path = Path(OUTPUT_FOLDER) / base_filename
        
        success = True
        
        # Export Excel
        if openpyxl:
            try:
                self.export_excel(f"{base_path}.xlsx")
            except Exception as e:
                print(f"[ERROR] Failed to export Excel: {e}")
                success = False
        else:
            print("Skipping Excel export (openpyxl not installed)")
        
        # Export JSON
        try:
            self.export_json(f"{base_path}_full.json")
        except Exception as e:
            print(f"[ERROR] Failed to export JSON: {e}")
            success = False
        
        # Export XML
        try:
            self.export_xml(f"{base_path}_full.xml")
        except Exception as e:
            print(f"[ERROR] Failed to export XML: {e}")
            success = False
        
        return success
    
    def export_excel(self, filepath):
        """Generates a flat Excel report of tags."""
        if not openpyxl:
            raise ImportError("openpyxl is required for Excel export")
        
        rows = []
        
        def flatten(parent, prefix, info):
            if isinstance(info, dict) and 'members' in info:
                for name, sub_info in sorted(info['members'].items()):
                    flatten(parent, f"{prefix}.{name}", sub_info)
            else:
                rows.append(['', f"{parent}{prefix}", str(info)])
        
        # Build flat structure
        for tag_name, tag_info in sorted(self.tags.items()):
            if isinstance(tag_info, dict) and 'members' in tag_info:
                rows.append([tag_name, '', tag_info.get('_data_type_', 'UDT')])
                for name, member_info in sorted(tag_info['members'].items()):
                    flatten(tag_name, f".{name}", member_info)
            else:
                rows.append([tag_name, tag_name, str(tag_info)])
        
        # Create Excel workbook
        print(f"\nGenerating Excel report with {len(rows)} rows...")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "PLC Tags"
        
        # Add headers
        ws.append(['Tag', 'Full Path', 'Data Type'])
        
        # Add data
        for row in rows:
            ws.append(row)
        
        # Format
        ws.auto_filter.ref = ws.dimensions
        ws.freeze_panes = 'A2'
        
        # Auto-adjust column widths
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value or '')) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 80)
            ws.column_dimensions[column].width = adjusted_width
        
        wb.save(filepath)
        print(f"Excel report saved to: {os.path.abspath(filepath)}")
    
    def export_json(self, filepath):
        """Saves tag data to a JSON file."""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.tags, f, indent=2, default=str)
        print(f"JSON report saved to: {os.path.abspath(filepath)}")
    
    def export_xml(self, filepath):
        """Saves tag data to an XML file."""
        root = ET.Element('PLCTagScan')
        
        def build_xml_node(parent, name, info):
            if isinstance(info, dict) and 'members' in info:
                node = ET.SubElement(parent, 'Tag', name=name, 
                                   dataType=info.get('_data_type_', 'STRUCT'))
                for member_name, member_info in info['members'].items():
                    build_xml_node(node, member_name, member_info)
            else:
                ET.SubElement(parent, 'Member', name=name, dataType=str(info))
        
        tags_root = ET.SubElement(root, 'Tags')
        for name, info in sorted(self.tags.items()):
            build_xml_node(tags_root, name, info)
        
        # Pretty print
        xml_string = ET.tostring(root, 'utf-8')
        dom = xml.dom.minidom.parseString(xml_string)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(dom.toprettyxml(indent="  "))
        
        print(f"XML report saved to: {os.path.abspath(filepath)}")
    
    # ==========================================================================
    # TAG READING & MONITORING METHODS
    # ==========================================================================
    
    def read_tag(self, tag_name, case_sensitive=False):
        """Reads a single tag value from the PLC."""
        if not self.plc or not self.plc.connected:
            raise Exception("Not connected to PLC")
        
        # Handle case-insensitive matching if requested
        if not case_sensitive and self.tags:
            matched_tag = self._find_case_insensitive_tag(tag_name)
            if matched_tag:
                tag_name = matched_tag
                print(f"--> Found case-insensitive match: '{tag_name}'")
        
        result = self.plc.read(tag_name)
        return result
    
    def _find_case_insensitive_tag(self, tag_name_in):
        """Finds the correct case for a tag name."""
        if '.' in tag_name_in:
            # Complex tag with members
            base_tag_in, member_path_in = tag_name_in.split('.', 1)
            
            # Find base tag
            base_match = None
            for tag in self.tags:
                if tag.lower() == base_tag_in.lower():
                    base_match = tag
                    break
            
            if not base_match:
                return None
            
            # Navigate member path
            current_level = self.tags[base_match]
            correct_path = [base_match]
            
            for part in member_path_in.split('.'):
                if isinstance(current_level, dict) and 'members' in current_level:
                    member_match = None
                    for member in current_level['members']:
                        if member.lower() == part.lower():
                            member_match = member
                            break
                    
                    if member_match:
                        correct_path.append(member_match)
                        current_level = current_level['members'][member_match]
                    else:
                        return None
                else:
                    return None
            
            return '.'.join(correct_path)
        else:
            # Simple tag
            for tag in self.tags:
                if tag.lower() == tag_name_in.lower():
                    return tag
            return None
    
    def monitor_tag(self, tag_name):
        """Continuously monitors a tag value with history."""
        if not self.plc or not self.plc.connected:
            raise Exception("Not connected to PLC")
        
        # Ensure we have the correct tag name
        if self.tags:
            matched = self._find_case_insensitive_tag(tag_name)
            if matched:
                tag_name = matched
        
        readings = deque(maxlen=MONITOR_HISTORY_SIZE)
        self.stop_monitoring.clear()
        
        # Start listener thread for ENTER key
        def listen_for_stop():
            input()
            self.stop_monitoring.set()
        
        listener = threading.Thread(target=listen_for_stop, daemon=True)
        listener.start()
        
        print(f"\n--- Monitoring '{tag_name}' ---")
        print("Press ENTER to stop...\n")
        
        while not self.stop_monitoring.is_set():
            try:
                result = self.plc.read(tag_name)
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                if result.error:
                    output = f"[{timestamp}] ERROR: {result.error}"
                else:
                    output = f"[{timestamp}] Value: {result.value} (Type: {result.type})"
                
                readings.append(output)
                
                # Display
                clear_screen()
                print(f"--- Monitoring '{tag_name}' (Last {len(readings)} readings) ---")
                print("Press ENTER to stop.\n")
                for reading in readings:
                    print(reading)
                
            except Exception as e:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                error_msg = f"[{timestamp}] ERROR: {e}"
                readings.append(error_msg)
            
            # Wait for refresh interval
            self.stop_monitoring.wait(MONITOR_REFRESH_SECONDS)
        
        print("\n--- Monitoring stopped ---")
    
    # ==========================================================================
    # USER INTERFACE METHODS
    # ==========================================================================
    
    def show_splash(self):
        """Displays the splash screen."""
        clear_screen()
        print(r"""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║      PLC Toolkit - Consolidated Edition                   ║
    ║                                                               ║
    ║           Tag Discovery • Export • Live Monitoring           ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
        """)
        print("                    Created by Scott Adams")
        print("\n")
    
    def run_discovery_workflow(self):
        """Runs the complete discovery workflow with user interaction."""
        print("\n--- Tag Discovery ---")
        print(f"Target: {self.ip} / Slot: {self.slot}")
        
        proceed = input("\nProceed with discovery? [Y/n]: ").strip().lower()
        if proceed == 'n':
            print("Discovery cancelled.")
            return False
        
        try:
            # Discover tags
            tags = animated_task(self.discover_tags, 
                               message="Discovering tags from PLC")
            
            print(f"\nDiscovered {len(tags)} tags.")
            
            # Store in database
            print("Storing tag data in database...")
            self.plc_id = self.db.update_plc_data(
                self.ip, self.slot, self.plc_info, tags
            )
            print("✓ Data stored successfully.")
            
            return True
            
        except Exception as e:
            print(f"\n[ERROR] Discovery failed: {e}")
            return False
    
    def run_export_workflow(self):
        """Runs the export workflow."""
        print("\n--- Export Tool ---")
        
        # Load tags if needed
        if not self.tags:
            if self.plc_id:
                print("Loading tags from database...")
                self.tags = self.db.get_tag_data(self.plc_id)
            else:
                print("[ERROR] No tag data available. Run discovery first.")
                return
        
        print(f"Ready to export {len(self.tags)} tags.")
        print("\nExport formats:")
        print("  • Excel (.xlsx) - Flat structure")
        print("  • JSON (.json) - Nested structure") 
        print("  • XML (.xml) - Hierarchical structure")
        
        proceed = input("\nProceed with export? [Y/n]: ").strip().lower()
        if proceed == 'n':
            print("Export cancelled.")
            return
        
        if self.export_all():
            print("\n✓ Export complete!")
        else:
            print("\n⚠ Export completed with some errors.")
    
    def run_tag_checker_workflow(self):
        """Runs the tag checking/monitoring workflow."""
        if not self.plc or not self.plc.connected:
            print("[ERROR] Not connected to PLC.")
            return
        
        # Load tags for case-insensitive matching
        if not self.tags and self.plc_id:
            print("Loading tag list from database...")
            self.tags = self.db.get_tag_data(self.plc_id)
        
        last_tag = None
        
        while True:
            print("\n--- Tag Checker Tool ---")
            
            if last_tag:
                print(f"\nOptions:")
                print(f"  c - Continue monitoring '{last_tag}'")
                print(f"  Enter tag name - Read a different tag")
                print(f"  ENTER - Return to menu")
                choice = input("\nYour choice: ").strip()
            else:
                choice = input("Enter tag name to read (or ENTER to return): ").strip()
            
            if not choice:
                break
            
            if choice.lower() == 'c' and last_tag:
                self.monitor_tag(last_tag)
                continue
            
            # Read single tag
            tag_name = choice
            print(f"\nReading '{tag_name}'...")
            
            try:
                result = self.read_tag(tag_name, case_sensitive=False)
                
                print("\n--- RESULT ---")
                print(f"  Tag: {result.tag}")
                print(f"Value: {result.value}")
                print(f" Type: {result.type}")
                if result.error:
                    print(f"Error: {result.error}")
                else:
                    last_tag = result.tag
                
            except Exception as e:
                print(f"\n[ERROR] {e}")
    
    def show_tools_menu(self):
        """Shows the tools menu after connection."""
        while True:
            if self.plc_info:
                rev = self.plc_info.get('revision', {})
                rev_str = f"{rev.get('major', '?')}.{rev.get('minor', '?')}"
                
                print("\n" + "=" * 60)
                print(f" Connected to: {self.plc_info.get('plc_name')} (Rev {rev_str})")
                print(f" IP: {self.ip} | Slot: {self.slot}")
                print("-" * 60)
                print(" Tools:")
                print("  1. Run Discovery (Update tag database)")
                print("  2. Export Tags (Excel, JSON, XML)")
                print("  3. Tag Checker (Read/monitor live values)")
                print("\n  9. Disconnect and exit")
                print("=" * 60)
                
                choice = input("Enter choice: ").strip()
                
                if choice == '1':
                    self.run_discovery_workflow()
                    input("\nPress Enter to continue...")
                elif choice == '2':
                    self.run_export_workflow()
                    input("\nPress Enter to continue...")
                elif choice == '3':
                    self.run_tag_checker_workflow()
                elif choice == '9':
                    break
                else:
                    print("Invalid choice.")
    
    def run(self):
        """Main entry point for the toolkit."""
        self.show_splash()
        
        try:
            # Get connection info
            print("Please enter connection details:")
            ip = input("  PLC IP Address: ").strip()
            slot_str = input("  Processor Slot [0]: ").strip() or '0'
            
            try:
                slot = int(slot_str)
            except ValueError:
                print("[ERROR] Invalid slot number.")
                return
            
            # Connect
            if not self.connect(ip, slot):
                print("\nConnection failed. Exiting.")
                return
            
            # Check for existing data
            print("\nChecking for existing tag data...")
            cursor = self.db.conn.cursor()
            result = cursor.execute(
                'SELECT id FROM plcs WHERE ip_address = ? AND slot = ?',
                (ip, slot)
            ).fetchone()
            
            if result:
                self.plc_id = result[0]
                print(f"Found existing data for this PLC (ID: {self.plc_id})")
                self.tags = self.db.get_tag_data(self.plc_id)
                print(f"Loaded {len(self.tags)} tags from database.")
            else:
                print("No existing data found. Run discovery to populate database.")
            
            # Show tools menu
            self.show_tools_menu()
            
        finally:
            # Clean up
            self.disconnect()
            self.db.close()
            print("\nExiting toolkit.")

# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

def main():
    """Main entry point."""
    try:
        toolkit = PLCToolkit()
        toolkit.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
