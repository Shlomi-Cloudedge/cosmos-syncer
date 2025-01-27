import os
import json
from azure.cosmos import CosmosClient, PartitionKey

class GitCosmosDBSynchronizer:
    def __init__(self, repo_path, cosmos_endpoint, cosmos_key):
        self.repo_path = repo_path
        self.cosmos_client = CosmosClient(cosmos_endpoint, credential=cosmos_key)

    def sync_repository(self):
        # Get existing databases
        existing_databases = [db['id'] for db in self.cosmos_client.list_databases()]
        local_databases = [d for d in os.listdir(self.repo_path) 
                           if os.path.isdir(os.path.join(self.repo_path, d)) and not d.startswith('.')]

        # # Delete databases not in local path
        # for db_name in existing_databases:
        #     if db_name not in local_databases:
        #         try:
        #             self.cosmos_client.delete_database(db_name)
        #             print(f"Deleted database {db_name}")
        #         except Exception as e:
        #             print(f"Error deleting database {db_name}: {e}")

        # Sync databases and containers
        for database_name in local_databases:
            database_path = os.path.join(self.repo_path, database_name)
            database = self.cosmos_client.create_database_if_not_exists(id=database_name)
            
            # Get existing containers in this database
            existing_containers = [c['id'] for c in database.list_containers()]
            local_containers = [d for d in os.listdir(database_path) 
                                if os.path.isdir(os.path.join(database_path, d)) and not d.startswith('.')]

            # # Delete containers not in local path
            # for container_name in existing_containers:
            #     if container_name not in local_containers:
            #         try:
            #             database.delete_container(container_name)
            #             print(f"Deleted container {container_name} in database {database_name}")
            #         except Exception as e:
            #             print(f"Error deleting container {container_name}: {e}")

            # Sync containers
            for container_name in local_containers:
                container_path = os.path.join(database_path, container_name)
                container = database.create_container_if_not_exists(
                    id=container_name, 
                    partition_key=PartitionKey(path="/id")
                )

                # Track existing documents
                local_docs = set()

                # Sync and upload JSON files
                for filename in os.listdir(container_path):
                    if filename.endswith('.json'):
                        file_path = os.path.join(container_path, filename)
                        
                        try:
                            with open(file_path, 'r') as file:
                                data = json.load(file)
                            
                            doc_id = data.get('id', os.path.splitext(filename)[0])
                            data['id'] = doc_id
                            local_docs.add(doc_id)
                            
                            container.upsert_item(body=data)
                            print(f"Uploaded {database_name}/{container_name}/{filename}")
                        
                        except Exception as e:
                            print(f"Error processing {file_path}: {e}")

                # # Delete documents not in local files
                # try:
                #     existing_docs = list(container.read_all_items())
                #     for doc in existing_docs:
                #         if doc['id'] not in local_docs:
                #             container.delete_item(item=doc, partition_key=doc['id'])
                #             print(f"Deleted {doc['id']} from {database_name}/{container_name}")
                # except Exception as e:
                #     print(f"Error checking for deletions: {e}")

    def run(self):
        self.sync_repository()

if __name__ == "__main__":
    synchronizer = GitCosmosDBSynchronizer(
        repo_path='./cosmos-sync',
        cosmos_endpoint=os.environ.get('COSMOS_ENDPOINT'),
        cosmos_key=os.environ.get('COSMOS_KEY')
    )
    synchronizer.run()