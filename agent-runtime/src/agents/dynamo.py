from agent_squad.storage import DynamoDbChatStorage
from agent_squad.orchestrator import AgentSquad


table_name = 'MemoryDynamoDBTable'
region = 'your-aws-region'
TTL_DURATION = 3600  # in seconds
dynamodb_storage = DynamoDbChatStorage(table_name, region, ttl_key='your-ttl-key-name', ttl_duration=TTL_DURATION)
orchestrator = AgentSquad(storage=dynamodb_storage)