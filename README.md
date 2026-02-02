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


<div align="center">

## 🏗️ Microservice Architecture Project

**Integrating Python & AI services with Java Spring ecosystem on AWS Cloud.**

<br>

### 💻 Core Stack & Languages

<img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white">
<img src="https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white">
<img src="https://img.shields.io/badge/OpenAI-412991?style=for-the-badge&logo=openai&logoColor=white">
&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;
<img src="https://img.shields.io/badge/Java-ED8B00?style=for-the-badge&logo=openjdk&logoColor=white">
<img src="https://img.shields.io/badge/Spring_Boot-6DB33F?style=for-the-badge&logo=spring-boot&logoColor=white">

<br>
<br>

### ☁️ AWS Cloud Infrastructure

**Compute & Networking**
<br>
<img src="https://img.shields.io/badge/AWS_Lambda-FF9900?style=for-the-badge&logo=aws-lambda&logoColor=white">
<img src="https://img.shields.io/badge/Amazon_ECS-FF9900?style=for-the-badge&logo=amazon-ecs&logoColor=white">
<img src="https://img.shields.io/badge/API_Gateway-FF9900?style=for-the-badge&logo=aws-api-gateway&logoColor=white">
<img src="https://img.shields.io/badge/ALB_(Load_Balancer)-8C4FFF?style=for-the-badge&logo=amazon-aws&logoColor=white">
<br>
<img src="https://img.shields.io/badge/Amazon_VPC-232F3E?style=for-the-badge&logo=amazon-aws&logoColor=white">
<img src="https://img.shields.io/badge/NAT_Gateway-232F3E?style=for-the-badge&logo=amazon-aws&logoColor=white">

<br>

**Storage, Database & Messaging**
<br>
<img src="https://img.shields.io/badge/Amazon_S3-569A31?style=for-the-badge&logo=amazon-s3&logoColor=white">
<img src="https://img.shields.io/badge/Amazon_DynamoDB-4053D6?style=for-the-badge&logo=amazon-dynamodb&logoColor=white">
<img src="https://img.shields.io/badge/Amazon_SQS-FF4F8B?style=for-the-badge&logo=amazon-sqs&logoColor=white">
<img src="https://img.shields.io/badge/Amazon_SNS-FF4F8B?style=for-the-badge&logo=amazon-sns&logoColor=white">

</div>
