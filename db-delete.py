#!/usr/bin/env python3
import os
import sys
from azure.cosmos import CosmosClient, exceptions

def delete_database(database_name: str , cosmos_endpoint: str , cosmos_key: str):

    if not cosmos_endpoint or not cosmos_key:
        print("Error: COSMOS_ENDPOINT and COSMOS_KEY environment variables must be set.")
        sys.exit(1)
    
    # Initialize the Cosmos client
    client = CosmosClient(cosmos_endpoint, cosmos_key)

    try:
        # Attempt to delete the database with the given name
        client.delete_database(database_name)
        print(f"Successfully deleted database '{database_name}' from Cosmos DB.")
    except exceptions.CosmosResourceNotFoundError:
        print(f"Database '{database_name}' not found in Cosmos DB.")
    except Exception as e:
        print(f"An error occurred while deleting database '{database_name}': {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Ensure the branch/database name is provided as an argument
    if len(sys.argv) != 2:
        print("Usage: python delete_db.py <branch-name>")
        sys.exit(1)
    
    branch_name = os.getenv("COSMOS_DB_NAME")
    cosmos_endpoint = os.environ.get("COSMOS_ENDPOINT")
    cosmos_key = os.environ.get("COSMOS_KEY")
    delete_database(branch_name , cosmos_endpoint , cosmos_key)
