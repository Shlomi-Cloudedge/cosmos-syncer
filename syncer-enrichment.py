import os
import json
from azure.cosmos import CosmosClient, PartitionKey


class GitCosmosDBSynchronizer:
    def __init__(self, repo_path, cosmos_endpoint, cosmos_key, db_name):
        self.repo_path = repo_path
        self.cosmos_client = CosmosClient(cosmos_endpoint, credential=cosmos_key)
        self.database_name = db_name
        self.valid_containers = ["enrichment", "enrichment_attributes"]

    def sync_repository(self):
        database = self.cosmos_client.create_database_if_not_exists(id=self.database_name)

        # Collect all local JSON files
        modified_files = []
        for root, dirs, files in os.walk(self.repo_path):
            for file in files:
                if file.endswith('.json'):
                    modified_files.append(os.path.join(root, file))

        # Keep track of synced document IDs for deletion checks
        synced_docs = {}

        for filename in modified_files:
            # Remove the repo_path prefix
            relative_path = filename.replace(self.repo_path + os.sep, "")

            # Split the path into parts
            parts = relative_path.split(os.sep)

            # Ensure there are at least 3 parts (repo_path, container, and file name)
            if len(parts) < 3:
                print(f"Skipping invalid path: {filename}")
                continue

            container_name, file_name = parts[1], parts[-1]

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

                # Track synced document ID
                if container_name not in synced_docs:
                    synced_docs[container_name] = set()
                synced_docs[container_name].add(doc_id)

                print(f"Modified {self.database_name}/{container_name}/{file_name}")

            except Exception as e:
                print(f"Error processing {filename}: {e}")

        # Check for and delete orphaned documents
        self.delete_orphaned_documents(database, synced_docs)


    def delete_orphaned_containers(self, database):
        """
        Delete containers from Cosmos DB that no longer have a corresponding local directory.
        """
        try:
            # Retrieve all containers in the database
            containers = list(database.list_containers())

            # Determine which containers are orphaned
            cosmos_container_names = {container['id'] for container in containers}
            local_container_names = set(self.valid_containers)
            orphaned_container_names = cosmos_container_names - local_container_names

            # Delete the orphaned containers
            for orphaned_name in orphaned_container_names:
                database.delete_container(container=orphaned_name)
                print(f"Deleted {self.database_name}/{orphaned_name}")

        except Exception as e:
            print(f"Error processing orphaned containers: {e}")

            
    def delete_orphaned_documents(self, database, synced_docs):
        """
        Delete documents from Cosmos DB that no longer have a corresponding local file.
        """
        try:
            # Retrieve all containers in the database
            containers = list(database.list_containers())

            for container_meta in containers:
                container_name = container_meta['id']
                container = database.get_container_client(container_name)

                # Query all documents in the container
                query = "SELECT c.id FROM c"
                documents = list(container.query_items(query=query, enable_cross_partition_query=True))

                # Determine which documents are orphaned
                cosmos_doc_ids = {doc['id'] for doc in documents}
                local_doc_ids = synced_docs.get(container_name, set())  # Default to an empty set if not in synced_docs
                orphaned_doc_ids = cosmos_doc_ids - local_doc_ids

                # Delete the orphaned documents
                for orphaned_id in orphaned_doc_ids:
                    container.delete_item(item=orphaned_id, partition_key=orphaned_id)
                    print(f"Deleted {self.database_name}/{container_name}/{orphaned_id}")

        except Exception as e:
            print(f"Error processing orphaned documents: {e}")

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