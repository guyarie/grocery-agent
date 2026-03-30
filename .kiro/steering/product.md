# Product Overview

## Agent Grocery — MCP Server for Claude Desktop

An MCP (Model Context Protocol) tool server that gives Claude Desktop the ability to manage grocery shopping via the Kroger API. Claude acts as a conversational grocery assistant — it remembers your preferences, searches products, and adds items to your Kroger cart.

### Core Features

- **Kroger OAuth2**: Connect your Kroger account via browser-based OAuth flow
- **Product Search**: Search Kroger's catalog with location-specific pricing and availability
- **Cart Management**: Add items to your Kroger cart by UPC, then check out on kroger.com
- **Store Location**: Find and set your preferred Kroger store by zip code
- **Agent Memory**: File-based long-term memory for grocery profile, shopping history, and receipt notes
- **Receipt Notes**: Save and retrieve receipt data as markdown files

### How It Works

Claude Desktop launches this MCP server as a stdio child process. The server exposes tools that Claude calls during conversation. All grocery intelligence (what to buy, brand preferences, substitutions) lives in Claude — the server just provides the Kroger API bridge and persistent storage.

### Target Users

People who use Claude Desktop and want a conversational grocery shopping assistant that learns their preferences and can build a Kroger cart from natural conversation.
