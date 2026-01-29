#!/usr/bin/python3
import os
import subprocess
import hashlib
import time
import sys
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from concurrent.futures import ThreadPoolExecutor
import argparse
import json
import tarfile
import tempfile
import shutil

# Default configuration content
DEFAULT_CONFIG = {
    "cluster": "78",
    "namespace": "nushare-cx-1-prod",
    "pod_name": "cx-fd3-glusterfs-slc-59d5f9c458-8x85d",
    "remote_path": "/mnt/vol_share_cx/workspace/common_scripts",
    "max_workers": 10,
    "debug": False,
    "show_concurrency": False,
    "exclude_paths": []
}

def load_sync_config(local_path, local_project_path=None):
    """Load sync configuration from hidden file in local path"""
    config_file = os.path.join(local_path, '.sync_config.json')
    
    if not os.path.exists(config_file):
        print(f"❌ Configuration file does not exist")
        print(f"📄 Expected location: {config_file}")
        print("\n🔧 Automatically creating default configuration file...")
        
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
            print(f"✅ Default configuration file created successfully")
            print(f"📄 Configuration file location: {config_file}")
            print("\n" + "=" * 60)
            print("📋 Please edit the configuration file with correct settings:")
            print("    "+"=" * 60)
            print(f"    📄 File path: {config_file}")
            print("    " + "=" * 60)
            print(json.dumps(DEFAULT_CONFIG, indent=4, ensure_ascii=False))
            print("=" * 60)
            print(f"\n💡 You can edit the configuration file using:")
            print(f"   vim {config_file}")
            print("\n⚠️  After editing the configuration file, please re-run the script")
            return None
        except Exception as e:
            print(f"❌ Failed to create configuration file: {e}")
            return None
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Validate required configuration items
        required_fields = ['cluster', 'namespace', 'pod_name', 'remote_path']
        missing_fields = [field for field in required_fields if field not in config]
        
        if missing_fields:
            print(f"❌ Configuration file missing required fields: {', '.join(missing_fields)}")
            return None
        
        # Set default values
        config.setdefault('max_workers', 10)
        config.setdefault('debug', False)
        config.setdefault('show_concurrency', False)
        config.setdefault('exclude_paths', [])

        # Validate configuration values
        if not isinstance(config['max_workers'], int) or config['max_workers'] <= 0:
            print(f"❌ Configuration file error: max_workers must be a positive integer, current value: {config['max_workers']}")
            return None

        if not isinstance(config['debug'], bool):
            print(f"❌ Configuration file error: debug must be a boolean value, current value: {config['debug']}")
            return None

        if not isinstance(config['show_concurrency'], bool):
            print(f"❌ Configuration file error: show_concurrency must be a boolean value, current value: {config['show_concurrency']}")
            return None

        if not isinstance(config['exclude_paths'], list):
            print(f"❌ Configuration file error: exclude_paths must be a list, current value: {config['exclude_paths']}")
            return None
        
        # Show configuration confirmation
        print(f"✅ Configuration file found: {config_file}")
        print("\n" + "=" * 60)
        print("📋 Current Configuration:")
        print("=" * 60)
        
        # 1. Pod信息
        print("🔧 Pod Information:")
        print(f"   🌐 Cluster: {config['cluster']}")
        print(f"   📋 Namespace: {config['namespace']}")
        print(f"   📦 Pod Name: {config['pod_name']}")
        print()
        
        # 2. 上传路径信息
        print("📂 Upload Path Information:")
        print(f"   📁 Local Project Path: {local_project_path or local_path}")
        print(f"   🎯 Remote Path: {config['remote_path']}")
        print()
        
        # 3. 其他配置
        print("⚙️  Other Configuration:")
        print(f"   ⚡ Max Concurrency: {config['max_workers']}")
        print(f"   🔍 Debug Mode: {'Enabled' if config['debug'] else 'Disabled'}")
        print(f"   📊 Detailed Concurrency Info: {'Enabled' if config['show_concurrency'] else 'Disabled'}")
        print(f"   🚫 Exclude Paths: {config['exclude_paths'] if config['exclude_paths'] else 'None'}")
        
        print("=" * 60)
        
        # Ask for confirmation
        print("\n❓ Please confirm the configuration is correct.")
        response = input("Press Enter to continue, or 'q' to quit: ").strip()
        
        if response.lower() == 'q':
            print("👋 Operation cancelled by user")
            return None
        
        print("🚀 Starting sync with the above configuration...")
        print("=" * 60)
        
        return config
    except json.JSONDecodeError as e:
        print(f"❌ Configuration file format error: {e}")
        return None
    except Exception as e:
        print(f"❌ Failed to read configuration file: {e}")
        return None

def init_config_file(local_path):
    """Initialize configuration file"""
    config_file = os.path.join(local_path, '.sync_config.json')
    
    if os.path.exists(config_file):
        print(f"⚠️  Configuration file already exists: {config_file}")
        response = input("Do you want to overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Operation cancelled")
            return
    
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        print(f"✅ Default configuration file created")
        print(f"📄 Configuration file location: {config_file}")
        print("Please edit this file with correct configuration information")
        print(f"\n💡 Tip: You can use the following command to edit the configuration file:")
        print(f"   vim {config_file}")
    except Exception as e:
        print(f"❌ Failed to create configuration file: {e}")

def calculate_file_md5(file_path):
    """Calculate MD5 hash of file"""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"Failed to calculate MD5 for {file_path}: {e}")
        return None

def format_file_size(size_bytes):
    """Format file size display"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"

def create_compressed_archive(local_path, debug=False, exclude_paths=None):
    """Create compressed tar.gz archive of local directory"""
    print("🗜️  Creating compressed archive...")

    # Set default value for exclude_paths
    if exclude_paths is None:
        exclude_paths = []

    # Create temporary file for archive
    temp_fd, temp_path = tempfile.mkstemp(suffix='.tar.gz', prefix='sync_archive_')
    os.close(temp_fd)  # Close file descriptor, we'll use tarfile to write
    
    try:
        # Calculate total size before compression
        total_size = 0
        file_count = 0
        for root, dirs, files in os.walk(local_path):
            # Exclude hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, local_path)
                if not any(part.startswith('.') for part in file_path.split(os.sep)):
                    # Check if file should be excluded
                    should_exclude = False
                    for exclude_path in exclude_paths:
                        if rel_path == exclude_path or rel_path.startswith(exclude_path + os.sep) or rel_path.startswith(exclude_path + '/'):
                            should_exclude = True
                            break

                    if not should_exclude:
                        total_size += os.path.getsize(file_path)
                        file_count += 1
        
        print(f"📊 Preparing to compress {file_count} files ({format_file_size(total_size)})")
        
        # Create compressed archive
        with tarfile.open(temp_path, 'w:gz') as tar:
            for root, dirs, files in os.walk(local_path):
                # Exclude hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, local_path)
                    # Skip files in hidden directories
                    if not any(part.startswith('.') for part in file_path.split(os.sep)):
                        # Check if file should be excluded
                        should_exclude = False
                        for exclude_path in exclude_paths:
                            if rel_path == exclude_path or rel_path.startswith(exclude_path + os.sep) or rel_path.startswith(exclude_path + '/'):
                                should_exclude = True
                                break

                        if not should_exclude:
                            arcname = os.path.relpath(file_path, local_path)
                            tar.add(file_path, arcname=arcname)
                            if debug:
                                print(f"🔧 DEBUG: Added to archive: {arcname}")
        
        # Get compressed size
        compressed_size = os.path.getsize(temp_path)
        compression_ratio = (1 - compressed_size / total_size) * 100 if total_size > 0 else 0
        
        print(f"✅ Archive created: {format_file_size(compressed_size)} (Compression ratio: {compression_ratio:.1f}%)")
        
        return temp_path, compressed_size, file_count
        
    except Exception as e:
        # Clean up on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise e

def upload_and_extract_archive(archive_path, pod_name, namespace, cluster, remote_path, debug=False):
    """Upload compressed archive to pod and extract it"""
    print("📤 Uploading compressed archive to pod...")
    
    # Upload archive to pod
    upload_command = f'tess kubectl --cluster {cluster} -n {namespace} cp {archive_path} {pod_name}:{remote_path}/sync_archive.tar.gz'
    
    if debug:
        print(f"🔧 DEBUG: Executing command: {upload_command}")
    
    try:
        subprocess.run(upload_command, shell=True, check=True)
        print("✅ Archive uploaded successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Archive upload failed: {e}")
        raise e
    
    # Extract archive in pod
    print("📦 Extracting archive in pod...")
    extract_command = f'tess kubectl --cluster {cluster} -n {namespace} exec {pod_name} -- bash -c "cd {remote_path} && tar -xzf sync_archive.tar.gz && rm sync_archive.tar.gz"'
    
    if debug:
        print(f"🔧 DEBUG: Executing command: {extract_command}")
    
    try:
        subprocess.run(extract_command, shell=True, check=True)
        print("✅ Archive extracted successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Archive extraction failed: {e}")
        raise e

def get_remote_files_md5(pod_name, namespace, cluster, remote_path, debug=False):
    """Get MD5 values of all files from Pod"""
    remote_files = {}
    try:
        # Get all files from remote directory
        command = f'tess kubectl --cluster {cluster} -n {namespace} exec {pod_name} -- find {remote_path} -type f -exec md5sum {{}} \\; 2>/dev/null || echo ""'
        if debug:
            print(f"🔧 DEBUG: Executing command: {command}")
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 2:
                        md5_value = parts[0]
                        file_path = ' '.join(parts[1:])
                        # Convert to relative path
                        if file_path.startswith(remote_path):
                            rel_path = file_path[len(remote_path):].lstrip('/')
                            remote_files[rel_path] = md5_value
                            if debug:
                                print(f"🔧 DEBUG: Remote file: {rel_path} -> {md5_value}")
    except Exception as e:
        print(f"Failed to get remote files MD5: {e}")
    
    return remote_files

class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, local_path, namespace, pod_name, remote_path, cluster, executor, debug=False, show_concurrency=False, exclude_paths=None):
        self.local_path = local_path
        self.namespace = namespace
        self.pod_name = pod_name
        self.remote_path = remote_path
        self.cluster = cluster
        self.executor = executor
        self.debug = debug
        self.show_concurrency = show_concurrency
        self.exclude_paths = exclude_paths if exclude_paths is not None else []
        self.processing_files = {}  # Track files being processed and their futures
    
    def get_active_tasks_count(self):
        """Get current number of active tasks"""
        return len([f for f in self.processing_files.values() if not f.done()])
    
    def get_active_files(self):
        """Get list of files currently being processed"""
        active_files = []
        for file_path, future in self.processing_files.items():
            if not future.done():
                rel_path = os.path.relpath(file_path, self.local_path)
                active_files.append(rel_path)
        return active_files
    
    def get_concurrency_info(self):
        """Get concurrency information"""
        active_tasks = self.get_active_tasks_count()
        max_workers = self.executor._max_workers
        total_processing = len(self.processing_files)
        completed_tasks = total_processing - active_tasks
        
        return {
            'active': active_tasks,
            'max': max_workers,
            'available': max_workers - active_tasks,
            'total_processing': total_processing,
            'completed': completed_tasks
        }
    
    def print_concurrency_status(self):
        """Print concurrency status"""
        concurrency_info = self.get_concurrency_info()
        active = concurrency_info['active']
        max_workers = concurrency_info['max']
        available = concurrency_info['available']
        total_processing = concurrency_info['total_processing']
        
        # Choose different icons based on concurrency level
        if active == 0:
            icon = "🟢"
        elif active < max_workers * 0.5:
            icon = "🟡"
        elif active < max_workers * 0.8:
            icon = "🟠"
        else:
            icon = "🔴"
        
        # Calculate usage percentage
        usage_percent = (active / max_workers) * 100 if max_workers > 0 else 0
        
        if self.show_concurrency:
            completed = concurrency_info['completed']
            print(f"{icon} Concurrency Status: {active}/{max_workers} (Available: {available}, Usage: {usage_percent:.1f}%, Total Processing: {total_processing}, Completed: {completed})")
            
            # If there are active tasks, show files being processed
            if active > 0:
                active_files = self.get_active_files()
                if active_files:
                    print(f"   Processing: {', '.join(active_files[:3])}{'...' if len(active_files) > 3 else ''}")
        else:
            # Simplified version, only show basic information
            completed = concurrency_info['completed']
            print(f"{icon} Concurrency: {active}/{max_workers} (Total Processing: {total_processing}, Completed: {completed})")

    def on_modified(self, event):
        if event.is_directory:
            return
        # Exclude files in hidden directories
        if any(part.startswith('.') for part in event.src_path.split(os.sep)):
            return

        # Check if file should be excluded based on exclude_paths
        rel_path = os.path.relpath(event.src_path, self.local_path)
        for exclude_path in self.exclude_paths:
            if rel_path == exclude_path or rel_path.startswith(exclude_path + os.sep) or rel_path.startswith(exclude_path + '/'):
                if self.debug:
                    print(f"🔧 DEBUG: Ignoring modified file: {rel_path} (matches exclude pattern: {exclude_path})")
                return

        self.upload_file(event.src_path)

    def on_created(self, event):
        if event.is_directory:
            return
        # Exclude files in hidden directories
        if any(part.startswith('.') for part in event.src_path.split(os.sep)):
            return

        # Check if file should be excluded based on exclude_paths
        rel_path = os.path.relpath(event.src_path, self.local_path)
        for exclude_path in self.exclude_paths:
            if rel_path == exclude_path or rel_path.startswith(exclude_path + os.sep) or rel_path.startswith(exclude_path + '/'):
                if self.debug:
                    print(f"🔧 DEBUG: Ignoring created file: {rel_path} (matches exclude pattern: {exclude_path})")
                return

        self.upload_file(event.src_path)

    def upload_file(self, file_path):
        rel_path = os.path.relpath(file_path, self.local_path)
        
        # Check if file is currently being processed
        if file_path in self.processing_files:
            old_future = self.processing_files[file_path]
            if not old_future.done():
                print(f"🔄 Cancelling old task, starting new sync: {rel_path}")
                old_future.cancel()  # Try to cancel old task
            else:
                print(f"🔍 File change detected: {rel_path}")
        else:
            print(f"🔍 File change detected: {rel_path}")
        
        # Submit new task
        future = self.executor.submit(self._upload_file, file_path)
        self.processing_files[file_path] = future
        
        # Show current concurrency
        if self.show_concurrency:
            self.print_concurrency_status()
        else:
            # Simplified version, only show basic concurrency info
            active = self.get_active_tasks_count()
            max_workers = self.executor._max_workers
            total_processing = len(self.processing_files)
            completed = total_processing - active
            print(f"📊 Concurrency: {active}/{max_workers} (Total Processing: {total_processing}, Completed: {completed})")

    def _upload_file(self, file_path):
        start_time = time.time()
        try:
            # Calculate relative path
            rel_path = os.path.relpath(file_path, self.local_path)
            # Get file size
            file_size = os.path.getsize(file_path)
            size_str = format_file_size(file_size)
            # Get remote directory path
            remote_dir = os.path.dirname(os.path.join(self.remote_path, rel_path))
            # Ensure remote directory exists
            mkdir_command = f'tess kubectl --cluster {self.cluster} -n {self.namespace} exec {self.pod_name} -- mkdir -p {remote_dir}'
            if self.debug:
                print(f"🔧 DEBUG: Executing command: {mkdir_command}")
            subprocess.run(mkdir_command, shell=True, check=True)
            # Upload file to corresponding remote path
            command = f'tess kubectl --cluster {self.cluster} -n {self.namespace} cp {file_path} {self.pod_name}:{os.path.join(self.remote_path, rel_path)}'
            
            # Retry mechanism
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if self.debug:
                        print(f"🔧 DEBUG: Executing command: {command}")
                    subprocess.run(command, shell=True, check=True)
                    end_time = time.time()
                    sync_time = end_time - start_time
                    if attempt > 0:
                        print(f"✅ File sync successful: {rel_path} (Time: {sync_time:.2f}s) (Retry {attempt} times before success) [Real-time sync]")
                    else:
                        print(f"✅ File sync successful: {rel_path} (Time: {sync_time:.2f}s) [Real-time sync]")
                    return
                except subprocess.CalledProcessError as e:
                    if attempt < max_retries - 1:
                        print(f"🔄 Retrying file sync: {rel_path} (Attempt {attempt + 1})")
                    else:
                        end_time = time.time()
                        sync_time = end_time - start_time
                        print(f"❌ File sync failed: {rel_path} - Error: {e} (Failed after {max_retries} retries) (Time: {sync_time:.2f}s)")
        finally:
            # Remove from processing list regardless of success or failure
            if file_path in self.processing_files:
                del self.processing_files[file_path]
            
            # Show current concurrency
            if self.show_concurrency:
                self.print_concurrency_status()
            else:
                # Simplified version, only show basic concurrency info
                active = self.get_active_tasks_count()
                max_workers = self.executor._max_workers
                total_processing = len(self.processing_files)
                completed = total_processing - active
                print(f"📊 Concurrency: {active}/{max_workers} (Total Processing: {total_processing}, Completed: {completed})")

def upload_initial_files(local_path, namespace, pod_name, remote_path, cluster, debug=False, max_workers=10, exclude_paths=None):
    start_time = time.time()
    
    # Ensure remote directory exists
    print("🔎 Checking remote directory and collecting remote inventory...")
    ensure_dir_cmd = f'tess kubectl --cluster {cluster} -n {namespace} exec {pod_name} -- mkdir -p {remote_path}'
    if debug:
        print(f"🔧 DEBUG: Executing command: {ensure_dir_cmd}")
    try:
        subprocess.run(ensure_dir_cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to ensure remote directory: {e}")
        return
    
    # Set default value for exclude_paths
    if exclude_paths is None:
        exclude_paths = []

    print("Getting remote files MD5 values...")
    remote_files_md5 = get_remote_files_md5(pod_name, namespace, cluster, remote_path, debug)
    print(f"Remote files count: {len(remote_files_md5)}")

    # Collect all directories to create and files to upload
    directories_to_create = set()
    files_to_upload = []
    files_skipped = 0
    
    for root, dirs, files in os.walk(local_path):
        # Exclude all hidden directories (directories starting with .)
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for file in files:
            file_path = os.path.join(root, file)
            # Calculate relative path
            rel_path = os.path.relpath(file_path, local_path)

            # Check if file should be excluded
            should_exclude = False
            for exclude_path in exclude_paths:
                # Support both exact match and prefix match
                if rel_path == exclude_path or rel_path.startswith(exclude_path + os.sep) or rel_path.startswith(exclude_path + '/'):
                    should_exclude = True
                    if debug:
                        print(f"🔧 DEBUG: Excluding file: {rel_path} (matches exclude pattern: {exclude_path})")
                    break

            if should_exclude:
                continue

            # Calculate local file MD5
            local_md5 = calculate_file_md5(file_path)
            
            # Check if upload is needed
            need_upload = True
            if rel_path in remote_files_md5:
                remote_md5 = remote_files_md5[rel_path]
                if local_md5 == remote_md5:
                    need_upload = False
                    files_skipped += 1
            
            if need_upload:
                # Get remote directory path
                remote_dir = os.path.dirname(os.path.join(remote_path, rel_path))
                directories_to_create.add(remote_dir)
                files_to_upload.append((file_path, rel_path))
    
    local_total_files = files_skipped + len(files_to_upload)
    print(f"📊 Inventory summary -> Remote: {len(remote_files_md5)} | Local: {local_total_files} | Pending: {len(files_to_upload)}")
    
    # Auto fast path if pending too large
    if len(files_to_upload) > 100:
        print("🗜️  Pending items exceed threshold (100). Using archive fast path...")
        try:
            archive_path, compressed_size, file_count = create_compressed_archive(local_path, debug, exclude_paths)
            if not archive_path.startswith('/tmp/'):
                tmp_archive = os.path.join('/tmp', os.path.basename(archive_path))
                shutil.move(archive_path, tmp_archive)
                archive_path = tmp_archive
            print(f"📦 Archive prepared at {archive_path} ({format_file_size(os.path.getsize(archive_path))})")
            remote_tmp_tar = "/tmp/sync_archive.tar.gz"
            upload_cmd = f'tess kubectl --cluster {cluster} -n {namespace} cp {archive_path} {pod_name}:{remote_tmp_tar}'
            if debug:
                print(f"🔧 DEBUG: Executing command: {upload_cmd}")
            subprocess.run(upload_cmd, shell=True, check=True)
            print("✅ Archive uploaded to pod /tmp")
            extract_cmd = f'tess kubectl --cluster {cluster} -n {namespace} exec {pod_name} -- bash -c "mkdir -p {remote_path} && tar -xzf {remote_tmp_tar} -C {remote_path} && rm -f {remote_tmp_tar}"'
            if debug:
                print(f"🔧 DEBUG: Executing command: {extract_cmd}")
            subprocess.run(extract_cmd, shell=True, check=True)
            print("✅ Archive extracted into remote path (overwrite)")
            try:
                os.unlink(archive_path)
            except Exception:
                pass
            end_time = time.time()
            total_time = end_time - start_time
            print(f"\n⏱️  Fast archive sync completed, total time: {total_time:.2f} seconds")
            print("=" * 60)
            print("🎉 Initial sync completed! Starting file change monitoring...")
            print("=" * 60)
            return
        except subprocess.CalledProcessError as e:
            print(f"❌ Archive fast path failed: {e}. Falling back to incremental upload.")
        except Exception as e:
            print(f"❌ Failed to prepare or upload archive: {e}. Falling back to incremental upload.")
    
    print("=" * 60)
    print("Starting incremental upload...")
    print("=" * 60)
    
    # Show directory creation commands
    if directories_to_create:
        # Organize directories, remove redundant parent directories
        sorted_dirs = sorted(directories_to_create)
        filtered_dirs = []
        
        for dir_path in sorted_dirs:
            # Check if this directory is a parent of other directories
            is_redundant = False
            for other_dir in sorted_dirs:
                if other_dir != dir_path and other_dir.startswith(dir_path + '/'):
                    is_redundant = True
                    break
            
            if not is_redundant:
                filtered_dirs.append(dir_path)
        
        if filtered_dirs:
            print(f"\n📁 Creating remote directories: {len(filtered_dirs)}")
        else:
            print(f"\n📁 No new directories to create")
    else:
        print(f"\n📁 No new directories to create")
    
    # No per-file listing for the first sync as requested
    if not files_to_upload:
        print(f"\n📄 No files to upload")
    
    print("=" * 60)
    print("Starting command execution...")
    print("=" * 60)
    
    # Batch create all required directories
    if directories_to_create:
        # Organize directories, remove redundant parent directories
        sorted_dirs = sorted(directories_to_create)
        filtered_dirs = []
        
        for dir_path in sorted_dirs:
            # Check if this directory is a parent of other directories
            is_redundant = False
            for other_dir in sorted_dirs:
                if other_dir != dir_path and other_dir.startswith(dir_path + '/'):
                    is_redundant = True
                    break
            
            if not is_redundant:
                filtered_dirs.append(dir_path)
        
        if filtered_dirs:
            print(f"\nCreating remote directories: {len(filtered_dirs)} directories (redundant parent directories filtered)")
            # Combine all directories into one command
            all_dirs = ' '.join(filtered_dirs)
            mkdir_command = f'tess kubectl --cluster {cluster} -n {namespace} exec {pod_name} -- mkdir -p {all_dirs}'
            if debug:
                print(f"🔧 DEBUG: Executing command: {mkdir_command}")
            try:
                subprocess.run(mkdir_command, shell=True, check=True)
                print(f"✅ Directory creation successful: {len(filtered_dirs)} directories")
                for remote_dir in filtered_dirs:
                    print(f"  - {remote_dir}")
            except subprocess.CalledProcessError as e:
                print(f"❌ Directory creation failed: {e}")
    
    # Concurrently upload all files
    if files_to_upload:
        print(f"\nStarting concurrent file upload... (Max concurrency: {max_workers})")
        
        # Variables for tracking progress
        completed_files = 0
        total_files = len(files_to_upload)
        
        def upload_single_file(file_info):
            nonlocal completed_files
            file_path, rel_path = file_info
            # Get file size
            file_size = os.path.getsize(file_path)
            size_str = format_file_size(file_size)
            print(f"📤 Uploading file: {rel_path} ({size_str})")
            command = f'tess kubectl --cluster {cluster} -n {namespace} cp {file_path} {pod_name}:{os.path.join(remote_path, rel_path)}'
            
            # Retry mechanism
            max_retries = 3
            start_time = time.time()
            for attempt in range(max_retries):
                try:
                    if debug:
                        print(f"🔧 DEBUG: Executing command: {command}")
                    subprocess.run(command, shell=True, check=True)
                    end_time = time.time()
                    sync_time = end_time - start_time
                    completed_files += 1
                    progress = (completed_files / total_files) * 100
                    if attempt > 0:
                        print(f"✅ File upload successful: {rel_path} (Time: {sync_time:.2f}s) (Retry {attempt} times before success) [{progress:.1f}%]")
                    else:
                        print(f"✅ File upload successful: {rel_path} (Time: {sync_time:.2f}s) [{progress:.1f}%]")
                    return True
                except subprocess.CalledProcessError as e:
                    if attempt < max_retries - 1:
                        print(f"🔄 Retrying file upload: {rel_path} (Attempt {attempt + 1})")
                    else:
                        end_time = time.time()
                        sync_time = end_time - start_time
                        completed_files += 1
                        progress = (completed_files / total_files) * 100
                        print(f"❌ File upload failed: {rel_path} - Error: {e} (Failed after {max_retries} retries) (Time: {sync_time:.2f}s) [{progress:.1f}%]")
                        return False
        
        # Use thread pool for concurrent upload
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            print(f"📊 Starting concurrent upload, max concurrency: {max_workers}")
            
            # Submit all upload tasks
            future_to_file = {executor.submit(upload_single_file, file_info): file_info for file_info in files_to_upload}
            
            # Wait for all tasks to complete and count results
            successful_uploads = 0
            failed_uploads = 0
            
            for future in future_to_file:
                try:
                    if future.result():
                        successful_uploads += 1
                    else:
                        failed_uploads += 1
                except Exception as e:
                    file_path = future_to_file[future][0]
                    print(f"❌ File upload exception: {file_path} - Error: {e}")
                    failed_uploads += 1
            
            print(f"\n📊 Upload completion statistics: ✅ {successful_uploads} successful, ❌ {failed_uploads} failed")
    else:
        print(f"\nNo files to upload")
    
    # Calculate total time
    end_time = time.time()
    total_time = end_time - start_time
    print(f"\n⏱️  Initial sync completed, total time: {total_time:.2f} seconds")
    print("=" * 60)
    print("🎉 Initial sync completed! Starting file change monitoring...")
    print("=" * 60)

def main():
    parser = argparse.ArgumentParser(
        description="Monitor local directory and upload files to Kubernetes Pod",
        epilog="""
Usage examples:
  # Initialize configuration file
  python sync_local_files_pod.py --local-project-path /Users/xchen17/workspace/common_scripts --init-config
  
  # Show current configuration
  python sync_local_files_pod.py --local-project-path /Users/xchen17/workspace/common_scripts --show-config
  
  # Start sync (using settings from configuration file)
  python sync_local_files_pod.py --local-project-path /Users/xchen17/workspace/common_scripts
  
  # Override settings in configuration file
  python sync_local_files_pod.py --local-project-path /Users/xchen17/workspace/common_scripts --max-workers 20 --debug --show-concurrency
  
  # Initial sync will auto-compress if pending > 100 files
  python sync_local_files_pod.py --local-project-path /Users/xchen17/workspace/common_scripts

Note: On first run, if configuration file doesn't exist, the script will ask whether to automatically create a default configuration file
        """
    )
    parser.add_argument('--local-project-path', required=True, help='Local project directory path (other parameters read from .sync_config.json file in this directory)')
    parser.add_argument('--init-config', action='store_true', help='Initialize configuration file (copy example file to local directory)')
    parser.add_argument('--show-config', action='store_true', help='Show current configuration information')
    parser.add_argument('--debug', action='store_true', help='Override debug setting in configuration file')
    parser.add_argument('--show-concurrency', action='store_true', help='Override show_concurrency setting in configuration file')
    parser.add_argument('--max-workers', type=int, help='Override max_workers setting in configuration file')

    args = parser.parse_args()

    # Validate local project path
    if not os.path.exists(args.local_project_path):
        print(f"❌ Error: Local project path does not exist: {args.local_project_path}")
        sys.exit(1)

    # If initialization of configuration file is specified
    if args.init_config:
        init_config_file(args.local_project_path)
        return

    # Load configuration file
    config = load_sync_config(args.local_project_path, args.local_project_path)
    if config is None:
        sys.exit(1)

    # If showing configuration is specified
    if args.show_config:
        config_file = os.path.join(args.local_project_path, '.sync_config.json')
        print("=" * 60)
        print("📋 Current configuration file content")
        print("=" * 60)
        print(f"📄 Configuration file location: {config_file}")
        print("=" * 60)
        print(json.dumps(config, indent=2, ensure_ascii=False))
        print("=" * 60)
        return

    # Command line arguments override configuration file settings
    final_config = config.copy()
    if args.max_workers is not None:
        if args.max_workers <= 0:
            print("❌ Error: --max-workers must be greater than 0")
            sys.exit(1)
        final_config['max_workers'] = args.max_workers
    if args.debug:
        final_config['debug'] = True
    if args.show_concurrency:
        final_config['show_concurrency'] = True

    # Show local project path information
    print(f"📁 Local project path: {args.local_project_path}")

    # Initial upload of all files
    upload_initial_files(args.local_project_path, final_config['namespace'], final_config['pod_name'], final_config['remote_path'], final_config['cluster'], final_config['debug'], final_config['max_workers'], final_config['exclude_paths'])

    # Set up directory monitoring
    print(f"Starting file change monitoring... (Max concurrency: {final_config['max_workers']})")
    with ThreadPoolExecutor(max_workers=final_config['max_workers']) as executor:  # Set maximum concurrent threads
        event_handler = FileChangeHandler(args.local_project_path, final_config['namespace'], final_config['pod_name'], final_config['remote_path'], final_config['cluster'], executor, final_config['debug'], final_config['show_concurrency'], final_config['exclude_paths'])
        observer = Observer()
        observer.schedule(event_handler, path=args.local_project_path, recursive=True)
        observer.start()

        try:
            while True:
                # Show current concurrency every 30 seconds (only when detailed concurrency info is enabled)
                time.sleep(30)
                if final_config['show_concurrency']:
                    concurrency_info = event_handler.get_concurrency_info()
                    if concurrency_info['active'] > 0:
                        event_handler.print_concurrency_status()
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

if __name__ == "__main__":
    main()