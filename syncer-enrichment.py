import os
import json
from azure.cosmos import CosmosClient, PartitionKey

class GitCosmosDBSynchronizer:
    def __init__(self, repo_path, cosmos_endpoint, cosmos_key , db_name):
        self.repo_path = repo_path
        self.cosmos_client = CosmosClient(cosmos_endpoint, credential=cosmos_key)
        self.database_name = db_name
        self.valid_containers = ["enrichment", "enrichment_attributes"]

    def sync_repository(self):
        database = self.cosmos_client.create_database_if_not_exists(id=self.database_name)

        # Find all items in all containers and list them as a path 
        cosmos_files = []

        for container_name in self.cosmos_client.get_database_client(self.database_name).list_container_names():
            container = database.get_container_client(container_name)
            for item in container.query_items(query="SELECT * FROM c", enable_cross_partition_query=True):
                cosmos_files.append(f"{container_name}/{item['id']}.json")
    
        # Find all JSON files in the repository


        modified_files = []
        for root, dirs, files in os.walk(self.repo_path):
            for file in files:
                if file.endswith('.json'):
                    modified_files.append(os.path.join(root, file))

        # If the file is in the Cosmos DB but not in the repository, delete it
        for filename in cosmos_files:
            if filename not in modified_files:
                container_name, file_name = filename.split('/')
                container = database.get_container_client(container_name)
                container.delete_item(item=file_name, partition_key=file_name)
                print(f"Deleted {self.database_name}/{container_name}/{file_name}")

        for filename in modified_files:
            # Remove the repo_path prefix (cosmos-sync/)
            relative_path = filename.replace(self.repo_path + os.sep, "")

            # Split the path into parts
            parts = relative_path.split(os.sep)

            # Ensure there are at least 3 parts (repo_path, container, and file name)
            if len(parts) < 3:
                print(f"Skipping invalid path: {filename}")
                continue

            container_name, file_name = parts[1], parts[-1]
            # OPTIONAL - if we want to ignore unknown containers , comment if we want to add new containers according to the file path
            # # Skip if the container is not valid
            # if container_name not in self.valid_containers:
            #     print(f"Skipping unknown container: {container_name}")
            #     continue

            try:
                # Ensure the container exists in the database
                container = database.create_container_if_not_exists(
                    id=container_name,
                    partition_key=PartitionKey(path="/id")
                )

                # Load and upsert the JSON file
                file_path = os.path.join(self.repo_path, relative_path)
                with open(file_path, 'r') as file:
                    data = json.load(file)

                # Use the 'id' field or the file name (without extension) as the document ID
                doc_id = data.get('id', os.path.splitext(file_name)[0])
                data['id'] = doc_id

                # Upsert the item into the container
                container.upsert_item(body=data)
                print(f"Modified {self.database_name}/{container_name}/{file_name}")

            except Exception as e:
                print(f"Error processing {filename}: {e}")

    def run(self):
        self.sync_repository()

if __name__ == "__main__":
    synchronizer = GitCosmosDBSynchronizer(
        repo_path='.',
        cosmos_endpoint=os.environ.get('COSMOS_ENDPOINT'),
        cosmos_key=os.environ.get('COSMOS_KEY'),
        db_name=os.environ.get('COSMOS_DB_NAME')
    )
    synchronizer.run()