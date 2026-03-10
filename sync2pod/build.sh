#!/bin/bash

rm -rf /usr/local/bin/sync_local_to_pod

cp ~/workspace/myscript/sync2pod/sync_local_to_pod.py /usr/local/bin/sync_local_to_pod

chmod +x /usr/local/bin/sync_local_to_pod
chmod 777 /usr/local/bin/sync_local_to_pod


sync_local_to_pod --project /Users/xchen17/workspace/patching-verify-contoller