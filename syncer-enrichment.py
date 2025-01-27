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

        modified_files = os.environ.get('MODIFIED_FILES', "").split()

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
            # OPTINAL - if we want to ignore unknown containers , comment if we want to add new containers according to the file path
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