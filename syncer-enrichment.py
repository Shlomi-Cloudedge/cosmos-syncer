import os
import json
from azure.cosmos import CosmosClient, PartitionKey

class GitCosmosDBSynchronizer:
   def __init__(self, repo_path, cosmos_endpoint, cosmos_key):
       self.repo_path = repo_path
       self.cosmos_client = CosmosClient(cosmos_endpoint, credential=cosmos_key)
       self.database_name = "shlomi"
       self.valid_containers = ["enrichment" , "enrichment_attributes"]

   def sync_repository(self):
       database = self.cosmos_client.create_database_if_not_exists(id=self.database_name)
       
       for container_name in self.valid_containers:
           container_path = os.path.join(self.repo_path, container_name)
           
           if not os.path.isdir(container_path):
               continue

           container = database.create_container_if_not_exists(
               id=container_name, 
               partition_key=PartitionKey(path="/id")
           )

           for filename in os.environ.get('MODIFIED_FILES').split():
                   file_path = os.path.join(container_path, filename)
                   
                   try:
                       with open(file_path, 'r') as file:
                           data = json.load(file)
                       
                       doc_id = data.get('id', os.path.splitext(filename)[0])
                       data['id'] = doc_id
                       
                       container.upsert_item(body=data)
                       print(f"Uploaded {self.database_name}/{container_name}/{filename}")
                   
                   except Exception as e:
                       print(f"Error processing {file_path}: {e}")

   def run(self):
       self.sync_repository()

if __name__ == "__main__":
   synchronizer = GitCosmosDBSynchronizer(
       repo_path='./cosmos-sync',
       cosmos_endpoint=os.environ.get('COSMOS_ENDPOINT'),
       cosmos_key=os.environ.get('COSMOS_KEY')
   )
   synchronizer.run()