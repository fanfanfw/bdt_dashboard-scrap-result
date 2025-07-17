from channels.generic.websocket import AsyncWebsocketConsumer
import json
import asyncio
import subprocess
import re
import os
import base64

class SyncNotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("sync_group", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("sync_group", self.channel_name)

    async def sync_message(self, event):
        await self.send(text_data=json.dumps(event["message"]))
        
class CronLogConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.log_file_id = self.scope['url_route']['kwargs']['log_file_id']
        
        # Create a safe group name - clean the log_file_id to be alphanumeric only
        import hashlib
        # Create a hash of the log_file_id for a safe group name
        safe_group_id = hashlib.md5(self.log_file_id.encode()).hexdigest()
        self.logs_group_name = f'cronlog_{safe_group_id}'
        self.should_stop = False
        
        # Join logs group
        await self.channel_layer.group_add(
            self.logs_group_name,
            self.channel_name
        )
        await self.accept()
        
        # Start the background task to stream logs
        asyncio.create_task(self.stream_logs())

    async def disconnect(self, close_code):
        # Stop the streaming logs task
        self.should_stop = True
        
        # Leave logs group
        await self.channel_layer.group_discard(
            self.logs_group_name,
            self.channel_name
        )
        
        # Don't try to send message after disconnect - this can cause issues
        print(f"Log consumer disconnected with code: {close_code}")
    
    async def validate_log_file(self, log_path):
        """Validate log file and return detailed info"""
        try:
            # Check existence
            if not os.path.exists(log_path):
                return False, f'Log file not found: {log_path}'
                
            if not os.path.isfile(log_path):
                return False, f'Path is not a file: {log_path}'
            
            # Get detailed file stats
            file_stats = os.stat(log_path)
            file_size = file_stats.st_size
            file_mode = oct(file_stats.st_mode)
            
            # Check permissions
            if not os.access(log_path, os.R_OK):
                return False, f'No read permission for file: {log_path} (mode: {file_mode})'
            
            # Additional checks for specific files
            allowed_paths = [
                '/home/scrapper/bdt_new_scrap/logs/file.log',
                '/home/scrapper/bdt_new_scrap/logs/file_carlist.log'
            ]
            
            if log_path not in allowed_paths:
                return False, f'Access denied to this log file: {log_path}'
            
            return True, f'File validation successful - Size: {file_size} bytes, Mode: {file_mode}'
            
        except Exception as e:
            return False, f'Validation error: {str(e)}'
    
    async def stream_logs(self):
        # Decode the base64 filename
        try:
            log_path = base64.b64decode(self.log_file_id).decode('utf-8')
            log_name = os.path.basename(log_path)
            
            # Send initial connection message with path info
            await self.send(text_data=json.dumps({
                'message': f'Attempting to connect to: {log_path}',
                'type': 'info'
            }))
            
            # Validate the log file
            is_valid, validation_message = await self.validate_log_file(log_path)
            
            await self.send(text_data=json.dumps({
                'message': validation_message,
                'type': 'info' if is_valid else 'error'
            }))
            
            if not is_valid:
                await self.send(text_data=json.dumps({
                    'error': validation_message
                }))
                return
                
            # Send initial connection message
            await self.send(text_data=json.dumps({
                'message': f'Connected to log stream for {log_name}',
                'type': 'info'
            }))
            
            # Check if tail command exists
            tail_command = '/usr/bin/tail'
            if not os.path.exists(tail_command):
                tail_command = '/bin/tail'
                if not os.path.exists(tail_command):
                    # Try to find tail in PATH
                    import shutil
                    tail_command = shutil.which('tail')
                    if not tail_command:
                        await self.send(text_data=json.dumps({
                            'error': 'tail command not found on system'
                        }))
                        return
                        
            await self.send(text_data=json.dumps({
                'message': f'Using tail command: {tail_command}',
                'type': 'info'
            }))
            
            # Initial log fetch - get the last 100 lines to start
            try:
                await self.send(text_data=json.dumps({
                    'message': f'Reading initial log content with: {tail_command} -n 100 {log_path}',
                    'type': 'info'
                }))
                
                process = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        tail_command, '-n', '100', log_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    ),
                    timeout=10.0  # 10 second timeout for process creation
                )
                
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=15.0  # 15 second timeout for reading
                )
                
                if process.returncode != 0:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    await self.send(text_data=json.dumps({
                        'error': f'Error reading log file (return code: {process.returncode}): {error_msg}'
                    }))
                    return
                    
                log_content = stdout.decode('utf-8', errors='replace')
                
                await self.send(text_data=json.dumps({
                    'message': f'Successfully read {len(log_content)} characters from log file',
                    'type': 'info'
                }))
                
                await self.send(text_data=json.dumps({
                    'log': log_content,
                    'type': 'initial'
                }))
                
                # Start tail -f process for real-time updates
                await self.send(text_data=json.dumps({
                    'message': f'Starting tail -f process for real-time monitoring...',
                    'type': 'info'
                }))
                
                try:
                    tail_process = await asyncio.wait_for(
                        asyncio.create_subprocess_exec(
                            tail_command, '-f', log_path,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        ),
                        timeout=10.0  # 10 second timeout for process creation
                    )
                    
                    # Check if process started successfully
                    await asyncio.sleep(0.5)  # Give it more time to start
                    if tail_process.returncode is not None:
                        stderr_output = await tail_process.stderr.read()
                        await self.send(text_data=json.dumps({
                            'error': f'tail -f process failed to start (code: {tail_process.returncode}): {stderr_output.decode()}'
                        }))
                        # Fall back to polling method immediately
                        raise Exception("tail -f failed to start")
                    
                    await self.send(text_data=json.dumps({
                        'message': f'tail -f process started successfully. PID: {tail_process.pid}',
                        'type': 'info'
                    }))
                    
                except Exception as tail_start_error:
                    await self.send(text_data=json.dumps({
                        'message': f'Could not start tail -f: {str(tail_start_error)}. Using polling method.',
                        'type': 'info'
                    }))
                    # Skip to polling method
                    raise Exception("Fallback to polling")
                
                # Read lines from tail -f in real-time
                await self.send(text_data=json.dumps({
                    'message': f'Real-time monitoring active. Waiting for new log entries...',
                    'type': 'info'
                }))
                
                while not self.should_stop and tail_process.returncode is None:
                    try:
                        # Read line with timeout
                        line = await asyncio.wait_for(
                            tail_process.stdout.readline(), 
                            timeout=2.0  # Increased timeout
                        )
                        
                        if line:
                            line_text = line.decode('utf-8', errors='replace').rstrip()
                            if line_text:  # Only send non-empty lines
                                # Get current full log (last 500 lines)
                                try:
                                    full_log_process = await asyncio.create_subprocess_exec(
                                        tail_command, '-n', '500', log_path,
                                        stdout=asyncio.subprocess.PIPE
                                    )
                                    full_stdout, _ = await full_log_process.communicate()
                                    full_content = full_stdout.decode('utf-8', errors='replace')
                                    
                                    await self.send(text_data=json.dumps({
                                        'log': full_content,
                                        'new_content': line_text,
                                        'type': 'update'
                                    }))
                                except Exception as e:
                                    await self.send(text_data=json.dumps({
                                        'error': f'Error getting full log content: {str(e)}'
                                    }))
                        else:
                            # If no line received, check if process is still running
                            if tail_process.returncode is not None:
                                await self.send(text_data=json.dumps({
                                    'message': f'tail process ended with code: {tail_process.returncode}',
                                    'type': 'info'
                                }))
                                break
                                
                    except asyncio.TimeoutError:
                        # No new data, continue loop
                        # Send a heartbeat message every few iterations
                        continue
                    except Exception as e:
                        await self.send(text_data=json.dumps({
                            'error': f'Error reading from tail: {str(e)}'
                        }))
                        break
                
                # Clean up tail process
                if tail_process.returncode is None:
                    tail_process.terminate()
                    try:
                        await asyncio.wait_for(tail_process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        tail_process.kill()
                        await tail_process.wait()
                
                await self.send(text_data=json.dumps({
                    'message': f'tail -f monitoring ended',
                    'type': 'info'
                }))
                        
            except Exception as e:
                # If tail -f fails, fall back to polling method
                await self.send(text_data=json.dumps({
                    'message': f'tail -f failed, falling back to polling method: {str(e)}',
                    'type': 'info'
                }))
                
                # Fallback: polling method
                try:
                    await self.send(text_data=json.dumps({
                        'message': f'Starting polling method for {log_name}...',
                        'type': 'info'
                    }))
                    
                    last_size = os.path.getsize(log_path)
                    poll_count = 0
                    
                    while not self.should_stop:
                        await asyncio.sleep(2)  # Poll every 2 seconds
                        poll_count += 1
                        
                        try:
                            current_size = os.path.getsize(log_path)
                            
                            # Send heartbeat every 30 seconds (15 polls)
                            if poll_count % 15 == 0:
                                await self.send(text_data=json.dumps({
                                    'message': f'Polling active... File size: {current_size} bytes',
                                    'type': 'info'
                                }))
                            
                            if current_size > last_size:
                                # File has new content
                                full_log_process = await asyncio.wait_for(
                                    asyncio.create_subprocess_exec(
                                        tail_command, '-n', '500', log_path,
                                        stdout=asyncio.subprocess.PIPE,
                                        stderr=asyncio.subprocess.PIPE
                                    ),
                                    timeout=10.0
                                )
                                stdout, stderr = await asyncio.wait_for(
                                    full_log_process.communicate(),
                                    timeout=15.0
                                )
                                
                                if full_log_process.returncode == 0:
                                    full_content = stdout.decode('utf-8', errors='replace')
                                    
                                    await self.send(text_data=json.dumps({
                                        'log': full_content,
                                        'new_content': f'File updated (polling mode) - size changed from {last_size} to {current_size}',
                                        'type': 'update'
                                    }))
                                    
                                    last_size = current_size
                                else:
                                    await self.send(text_data=json.dumps({
                                        'error': f'Error reading updated content: {stderr.decode() if stderr else "Unknown error"}'
                                    }))
                        except Exception as poll_error:
                            await self.send(text_data=json.dumps({
                                'error': f'Error during polling: {str(poll_error)}'
                            }))
                            
                except Exception as fallback_error:
                    await self.send(text_data=json.dumps({
                        'error': f'Polling fallback also failed: {str(fallback_error)}'
                    }))
                
        except Exception as decode_error:
            # Handle base64 decode errors
            await self.send(text_data=json.dumps({
                'error': f'Invalid log file ID or decode error: {str(decode_error)}'
            }))
        except asyncio.TimeoutError:
            await self.send(text_data=json.dumps({
                'error': 'Operation timed out - the log file might be too large or inaccessible'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'error': f'Fatal error in log streaming: {str(e)}'
            }))
            
    async def receive(self, text_data):
        data = json.loads(text_data)
        
        if data.get('command') == 'stop':
            self.should_stop = True
            await self.send(text_data=json.dumps({
                'message': 'Stopped log streaming',
                'type': 'info'
            }))

