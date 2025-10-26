#!/bin/bash

# Start the action server in the background
rasa run actions &

# Start the main rasa server
rasa run --enable-api --cors "*" --port $PORT
