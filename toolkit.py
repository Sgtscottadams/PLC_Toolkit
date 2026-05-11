#!/usr/bin/env python3
"""
PLC Toolkit - Main Hub
Handles PLC connection, initial tag discovery, database storage, and the main tool menu.
"""

import os
import sys
import json
import sqlite3
import threading
import time
from datetime import datetime
from pycomm3 import LogixDriver

# Import the tool modules
import export_tool
import tag_checker_tool

DATABASE_FILE = 'plc_data.db'

def clear_screen():
    """Clears the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def show_splash_screen():
    """Displays the initial ASCII art splash screen."""
    clear_screen()
    print(r"""
                                                                                                                                                                           dddddddd
               AAA               lllllll lllllll                                                        BBBBBBBBBBBBBBBBB                                                  d::::::dlllllll
              A:::A              l:::::l l:::::l                                                        B::::::::::::::::B                                                 d::::::dl:::::l
             A:::::A             l:::::l l:::::l                                                        B::::::BBBBBB:::::B                                                d::::::dl:::::l
            A:::::::A            l:::::l l:::::l                                                        BB:::::B     B:::::B                                               d:::::d l:::::l
           A:::::::::A            l::::l  l::::l     eeeeeeeeeeee    nnnn  nnnnnnnn                       B::::B     B:::::Brrrrr   rrrrrrrrr   aaaaaaaaaaaaa      ddddddddd:::::d  l::::l     eeeeeeeeeeee  yyyyyyy           yyyyyyy
          A:::::A:::::A           l::::l  l::::l   ee::::::::::::ee  n:::nn::::::::nn                     B::::B     B:::::Br::::rrr:::::::::r  a::::::::::::a   dd::::::::::::::d  l::::l   ee::::::::::::ee y:::::y         y:::::y
         A:::::A A:::::A          l::::l  l::::l  e::::::eeeee:::::een::::::::::::::nn                    B::::BBBBBB:::::B r:::::::::::::::::r aaaaaaaaa:::::a d::::::::::::::::d  l::::l  e::::::eeeee:::::eey:::::y       y:::::y
        A:::::A   A:::::A         l::::l  l::::l e::::::e     e:::::enn:::::::::::::::n ---------------   B:::::::::::::BB  rr::::::rrrrr::::::r         a::::ad:::::::ddddd:::::d  l::::l e::::::e     e:::::e y:::::y     y:::::y
       A:::::A     A:::::A        l::::l  l::::l e:::::::eeeee::::::e  n:::::nnnn:::::n -:::::::::::::-   B::::BBBBBB:::::B  r:::::r     r:::::r  aaaaaaa:::::ad::::::d    d:::::d  l::::l e:::::::eeeee::::::e  y:::::y   y:::::y
      A:::::AAAAAAAAA:::::A       l::::l  l::::l e:::::::::::::::::e   n::::n    n::::n ---------------   B::::B     B:::::B r:::::r     rrrrrrraa::::::::::::ad:::::d     d:::::d  l::::l e:::::::::::::::::e    y:::::y y:::::y
     A:::::::::::::::::::::A      l::::l  l::::l e::::::eeeeeeeeeee    n::::n    n::::n                   B::::B     B:::::B r:::::r           a::::aaaa::::::ad:::::d     d:::::d  l::::l e::::::eeeeeeeeeee      y:::::y:::::y
    A:::::AAAAAAAAAAAAA:::::A     l::::l  l::::l e:::::::e             n::::n    n::::n                   B::::B     B:::::B r:::::r          a::::a    a:::::ad:::::d     d:::::d  l::::l e:::::::e                y:::::::::y
   A:::::A             A:::::A   l::::::ll::::::le::::::::e            n::::n    n::::n                 BB:::::BBBBBB::::::B r:::::r          a::::a    a:::::ad::::::ddddd::::::ddl::::::le::::::::e                y:::::::y
  A:::::A               A:::::A  l::::::ll::::::l e::::::::eeeeeeee    n::::n    n::::n                 B:::::::::::::::::B  r:::::r          a:::::aaaa::::::a d:::::::::::::::::dl::::::l e::::::::eeeeeeee         y:::::y
 A:::::A                 A:::::A l::::::ll::::::l  ee:::::::::::::e    n::::n    n::::n                 B::::::::::::::::B   r:::::r           a::::::::::aa:::a d:::::::::ddd::::dl::::::l  ee:::::::::::::e        y:::::y
AAAAAAA                   AAAAAAAllllllllllllllll    eeeeeeeeeeeeee    nnnnnn    nnnnnn                 BBBBBBBBBBBBBBBBB    rrrrrrr            aaaaaaaaaa  aaaa  ddddddddd   dddddllllllll    eeeeeeeeeeeeee       y:::::y
                                                                                                                                                                                                                   y:::::y
                                                                                                                                                                                                                  y:::::y
                                                                                                                                                                                                                 y:::::y
                                                                                                                                                                                                                y:::::y
                                                                                                                                                                                                               yyyyyyy



TTTTTTTTTTTTTTTTTTTTTTT                               lllllll kkkkkkkk             iiii          tttt
T:::::::::::::::::::::T                               l:::::l k::::::k            i::::i      ttt:::t
T:::::::::::::::::::::T                               l:::::l k::::::k             iiii       t:::::t
T:::::TT:::::::TT:::::T                               l:::::l k::::::k                        t:::::t
TTTTTT  T:::::T  TTTTTTooooooooooo      ooooooooooo    l::::l  k:::::k    kkkkkkkiiiiiiittttttt:::::ttttttt
        T:::::T      oo:::::::::::oo  oo:::::::::::oo  l::::l  k:::::k   k:::::k i:::::it:::::::::::::::::t
        T:::::T     o:::::::::::::::oo:::::::::::::::o l::::l  k:::::k  k:::::k   i::::it:::::::::::::::::t
        T:::::T     o:::::ooooo:::::oo:::::ooooo:::::o l::::l  k:::::k k:::::k    i::::itttttt:::::::tttttt
        T:::::T     o::::o     o::::oo::::o     o::::o l::::l  k::::::k:::::k     i::::i      t:::::t
        T:::::T     o::::o     o::::oo::::o     o::::o l::::l  k:::::::::::k      i::::i      t:::::t
        T:::::T     o::::o     o::::oo::::o     o::::o l::::l  k:::::::::::k      i::::i      t:::::t
        T:::::T     o::::o     o::::oo::::o     o::::o l::::l  k::::::k:::::k     i::::i      t:::::t    tttttt
      TT:::::::TT   o:::::ooooo:::::oo:::::ooooo:::::ol::::::lk::::::k k:::::k   i::::::i     t::::::tttt:::::t
      T:::::::::T   o:::::::::::::::oo:::::::::::::::ol::::::lk::::::k  k:::::k  i::::::i     tt::::::::::::::t
      T:::::::::T    oo:::::::::::oo  oo:::::::::::oo l::::::lk::::::k   k:::::k i::::::i       tt:::::::::::tt
      TTTTTTTTTTT      ooooooooooo      ooooooooooo   llllllllkkkkkkkk    kkkkkkkiiiiiiii         ttttttttttt
    """)
    print("=" * 60)
    print(" " * 42 + "Created by Scott Adams")
    print("\n" * 2)

def get_connection_info():
    """Prompts the user for PLC connection details."""
    print("\nPlease Enter Connection Details:")
    ip = input("  Enter PLC IP Address: ").strip()
    slot_str = input("  Enter Processor Slot [0]: ").strip() or '0'
    try:
        slot = int(slot_str)
        return ip, slot
    except ValueError:
        print("\n[ERROR] Invalid slot number. Please enter a valid integer.")
        return None, None

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
        
        plc_id = cursor.execute('SELECT id FROM plcs WHERE ip_address = ? AND slot = ?', (ip, slot)).fetchone()[0]
        
        tags_json = json.dumps(tags)
        cursor.execute('''
            INSERT INTO tag_data (plc_id, tags_json)
            VALUES (?, ?)
            ON CONFLICT(plc_id) DO UPDATE SET
                tags_json=excluded.tags_json
        ''', (plc_id, tags_json))
        
        self.conn.commit()
        return plc_id

    def close(self):
        """Closes the database connection."""
        self.conn.close()

def animated_task(target_func, *args, **kwargs):
    """
    Runs a function in a separate thread while showing a "working" animation.
    """
    message = kwargs.get('message', 'Working')
    sys.stdout.write(message + " ")
    
    done_event = threading.Event()
    
    def task_wrapper():
        target_func(*args)
        done_event.set()

    thread = threading.Thread(target=task_wrapper)
    thread.start()

    while not done_event.is_set():
        sys.stdout.write('.')
        sys.stdout.flush()
        time.sleep(0.5)
    
    thread.join()

def _parse_structure_def(tag_def):
    """
    Recursively parses a raw tag definition into a simple, JSON-serializable format.
    """
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
            structure['members'][member_name] = _parse_structure_def(member_data)
    
    return structure

def connect_and_discover(ip, slot, results):
    """
    Connects to the PLC, discovers all tags, and stores the fully processed,
    JSON-serializable definitions in the results dict.
    """
    plc = None
    try:
        plc = LogixDriver(ip, slot=slot, timeout=10, init_tags=False)
        plc.open()
        
        initial_tag_list = []
        controller_tags = plc.get_tag_list()
        if controller_tags:
            initial_tag_list.extend(controller_tags)
        
        try:
            programs_tag = plc.read('PROGRAM')
            if programs_tag and programs_tag.value:
                for prog_name in programs_tag.value:
                    try:
                        program_tags = plc.get_tag_list(program=prog_name)
                        if program_tags:
                            for tag in program_tags:
                                tag['tag_name'] = f"Program:{prog_name}.{tag['tag_name']}"
                            initial_tag_list.extend(program_tags)
                    except Exception: pass
        except Exception: pass

        parsed_tags = {}
        total = len(initial_tag_list)
        sys.stdout.write(f"\rReading {total} Tags ")
        
        for i, summary in enumerate(initial_tag_list):
            name = summary.get('tag_name')
            if not name or name.startswith('__') or name.startswith('System:'):
                continue
            try:
                full_def = plc.get_tag_info(name)
                parsed_tags[name] = _parse_structure_def(full_def)
            except Exception:
                dt = summary.get('data_type', 'UNKNOWN')
                if hasattr(dt, 'name'):
                    parsed_tags[name] = dt.name
                else:
                    parsed_tags[name] = str(dt)

            if (i + 1) % 10 == 0 or i + 1 == total:
                 sys.stdout.write('.')
                 sys.stdout.flush()

        results['plc'] = plc
        results['info'] = plc.get_plc_info()
        results['tags'] = parsed_tags
        results['error'] = None

    except Exception as e:
        results['error'] = str(e)
        if plc and plc.connected:
            plc.close()

def show_tools_menu(plc, ip, slot, db_manager, plc_id):
    """Displays the main tool menu after a successful connection."""
    while True:
        info = plc.get_plc_info()
        rev = info.get('revision', {})
        rev_str = f"{rev.get('major', '?')}.{rev.get('minor', '?')}"
        
        print("\n\n" + "=" * 60)
        print(f" Connected to: {info.get('plc_name')} (Rev {rev_str})")
        print(f" IP: {ip} | Slot: {slot}")
        print("-" * 60)
        print(" Please select a tool to run:")
        print("  1. Export Tool (Generate Reports)")
        print("  2. Tag Checker Tool (Read Live Value)")
        print("\n  9. Disconnect and Return to Main Menu")
        print("=" * 60)
        
        choice = input("Enter your choice: ").strip()

        if choice == '1':
            export_tool.run_exporter(db_manager.conn, plc_id)
            input("\nPress Enter to return to the tools menu...")
        elif choice == '2':
            tag_checker_tool.run_checker(plc, db_manager.conn, plc_id)
        elif choice == '9':
            print("Disconnecting...")
            plc.close()
            print("Disconnected.")
            break
        else:
            print("Invalid choice. Please try again.")

def main():
    """Main application loop."""
    db = DatabaseManager(DATABASE_FILE)

    while True:
        show_splash_screen()
        choice = input("Press ENTER to begin, or 'q' to quit: ").strip().lower()
        if choice == 'q':
            break
        
        ip, slot = get_connection_info()
        if not ip:
            input("\nPress Enter to return to the main menu...")
            continue
        
        results = {}
        animated_task(connect_and_discover, ip, slot, results, message="Connecting and Discovering Tags")
        print(" DONE")
        
        if results.get('error'):
            print(f"\n[ERROR] Connection failed: {results['error']}")
            input("\nPress Enter to return to the main menu...")
            continue

        plc = results['plc']
        info = results['info']
        tags_data = results['tags']
        
        print("\nStoring PLC data and tags locally...")
        plc_id = db.update_plc_data(ip, slot, info, tags_data)
        print("✓ Data stored successfully.")

        if plc:
            show_tools_menu(plc, ip, slot, db, plc_id)
        else:
            input("\nAn unknown error occurred. Press Enter to return to the main menu...")
    
    db.close()
    print("Exiting Toolkit.")

if __name__ == "__main__":
    main()

