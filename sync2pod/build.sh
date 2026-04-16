#!/bin/bash

rm -rf /usr/local/bin/sync_local_to_pod

chmod +x sync_local_to_pod.py
chmod 777 sync_local_to_pod.py

ln -s ~/workspace/myscript/sync2pod/sync_local_to_pod.py /usr/local/bin/sync_local_to_pod

sync_local_to_pod -h