<img src="AWS구성 (캡스톤).jpg">

<h2>Processing</h2>
<label>1. User PDF upload </label><br>
<label>2. PDF upload logic to Spring S3 </label><br>
3. PDF Bucket PUT event occurs and SQS trigger <br>
4. PDF Event SQS message creation <br>
5. Python Backend After receiving SQS message, download PDF from S3 and extract PDF words, normalization logic <br>
6. DynamoDB Function Normalized words are looked up with DynamoDB and missing word augmentation logic and stored in JSON Bucket <br>
7. JSON Bucket storage and SQS trigger <br>
8. Spring Trigger SQS Spring task completion message confirmation <br>
9. Spring Backend JSON request to API Gateway after task completion confirmation <br>
10. kanji/{book_name} for API Gateway GET request <br>
11. JSON GET Function JSON file in S3 through value for request received by API Gateway API… <br>
