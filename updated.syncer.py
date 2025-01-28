import os
import json
import logging
from typing import List, Set
from pathlib import Path
from azure.cosmos import CosmosClient, PartitionKey, exceptions
from dataclasses import dataclass

@dataclass
class SyncStats:
    updated: int = 0
    deleted: int = 0
    errors: int = 0

class GitCosmosDBSynchronizer:
    def __init__(self, repo_path: str, cosmos_endpoint: str, cosmos_key: str, db_name: str):
        """Initialize the synchronizer with required parameters."""
        self.repo_path = Path(repo_path).resolve()
        self.cosmos_client = CosmosClient(cosmos_endpoint, credential=cosmos_key)
        self.database_name = db_name
        self.stats = SyncStats()
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def get_cosmos_files(self) -> Set[str]:
        """Get all files currently in CosmosDB."""
        cosmos_files = set()
        database = self.cosmos_client.get_database_client(self.database_name)
        
        try:
            for container_name in database.list_containers():
                container = database.get_container_client(container_name['id'])
                try:
                    items = container.query_items(
                        query="SELECT c.id FROM c",
                        enable_cross_partition_query=True
                    )
                    for item in items:
                        cosmos_files.add(f"{container_name['id']}/{item['id']}.json")
                except exceptions.CosmosHttpResponseError as e:
                    self.logger.error(f"Error querying container {container_name['id']}: {e}")
                    self.stats.errors += 1
        except exceptions.CosmosHttpResponseError as e:
            self.logger.error(f"Error listing containers: {e}")
            self.stats.errors += 1
            
        return cosmos_files

    def get_local_files(self) -> Set[str]:
        """Get all JSON files in the repository."""
        local_files = set()
        
        try:
            for file_path in self.repo_path.rglob('*.json'):
                relative_path = file_path.relative_to(self.repo_path)
                if len(relative_path.parts) >= 2:  # Must have at least container/file.json
                    local_files.add(str(relative_path))
        except Exception as e:
            self.logger.error(f"Error scanning local files: {e}")
            self.stats.errors += 1
            
        return local_files

    def delete_cosmos_item(self, container_name: str, file_name: str) -> bool:
        """Delete an item from CosmosDB."""
        try:
            database = self.cosmos_client.get_database_client(self.database_name)
            container = database.get_container_client(container_name)
            
            item_id = Path(file_name).stem  # Remove .json extension
            container.delete_item(item=item_id, partition_key=item_id)
            
            self.logger.info(f"Deleted {self.database_name}/{container_name}/{file_name}")
            self.stats.deleted += 1
            return True
        except exceptions.CosmosHttpResponseError as e:
            self.logger.error(f"Error deleting {container_name}/{file_name}: {e}")
            self.stats.errors += 1
            return False

    def upsert_cosmos_item(self, container_name: str, file_path: Path) -> bool:
        """Upsert an item to CosmosDB."""
        try:
            database = self.cosmos_client.get_database_client(self.database_name)
            
            # Create container if it doesn't exist
            container = database.create_container_if_not_exists(
                id=container_name,
                partition_key=PartitionKey(path="/id")
            )

            # Load and validate JSON data
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Ensure ID exists
            if 'id' not in data:
                data['id'] = file_path.stem

            # Upsert the item
            container.upsert_item(body=data)
            self.logger.info(f"Upserted {self.database_name}/{container_name}/{file_path.name}")
            self.stats.updated += 1
            return True
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in {file_path}: {e}")
            self.stats.errors += 1
            return False
        except exceptions.CosmosHttpResponseError as e:
            self.logger.error(f"Cosmos DB error for {file_path}: {e}")
            self.stats.errors += 1
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error processing {file_path}: {e}")
            self.stats.errors += 1
            return False

    def sync_repository(self) -> SyncStats:
        """Synchronize repository with CosmosDB."""
        self.logger.info("Starting synchronization...")
        
        # Get files from both sources
        cosmos_files = self.get_cosmos_files()
        local_files = self.get_local_files()

        # Delete files that exist in Cosmos but not locally
        for cosmos_file in cosmos_files - local_files:
            container_name = Path(cosmos_file).parts[0]
            file_name = Path(cosmos_file).name
            self.delete_cosmos_item(container_name, file_name)

        # Update or add local files
        for local_file in local_files:
            container_name = Path(local_file).parts[0]
            full_path = self.repo_path / local_file
            self.upsert_cosmos_item(container_name, full_path)

        self.logger.info(f"""
Synchronization completed:
- Updated: {self.stats.updated}
- Deleted: {self.stats.deleted}
- Errors: {self.stats.errors}
""")
        
        return self.stats

    def run(self) -> SyncStats:
        """Main execution method."""
        try:
            return self.sync_repository()
        except Exception as e:
            self.logger.error(f"Fatal error during synchronization: {e}")
            self.stats.errors += 1
            return self.stats

def main():
    """Main entry point with environment validation."""
    required_env_vars = ['COSMOS_ENDPOINT', 'COSMOS_KEY', 'COSMOS_DB_NAME']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"Missing required environment variables: {', '.join(missing_vars)}")
        exit(1)
    
    synchronizer = GitCosmosDBSynchronizer(
        repo_path='.',
        cosmos_endpoint=os.environ['COSMOS_ENDPOINT'],
        cosmos_key=os.environ['COSMOS_KEY'],
        db_name=os.environ['COSMOS_DB_NAME']
    )
    
    stats = synchronizer.run()
    if stats.errors > 0:
        exit(1)

if __name__ == "__main__":
    main()