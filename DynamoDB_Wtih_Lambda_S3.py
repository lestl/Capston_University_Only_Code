import os
import json
import boto3
import re
import time
import google.generativeai as genai

# =================================================================
# 1. 초기화 (핸들러 함수 밖에서 실행하여 재사용)
# =================================================================
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
DYNAMODB_TABLE_NAME = os.getenv('DYNAMODB_TABLE_NAME')
S3_RESULTS_BUCKET = os.getenv('S3_RESULTS_BUCKET') # 최종 JSON을 저장할 S3 버킷
SQS_NOTIFICATION_URL = os.getenv('SQS_NOTIFICATION_URL') # Spring 알림용 SQS URL

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")
dynamodb_client = boto3.client('dynamodb')
s3_client = boto3.client('s3')
sqs_client = boto3.client('sqs')

# =================================================================
# Helper Functions
# =================================================================

def generate_ai_data(kanji_list, batch_size=100):
    """Gemini AI를 사용하여 찾지 못한 한자 데이터를 생성합니다."""
    if not kanji_list:
        return []
    results = []
    for i in range(0, len(kanji_list), batch_size):
        batch = kanji_list[i:i + batch_size]
        batch_str = ", ".join(batch)
        print(f"AI 데이터 생성 시작: 배치 {i // batch_size + 1} ({len(batch)} 한자)")
        prompt = f"""다음 일본 한자에 대한 정보를 JSON 배열 형태로 생성해주세요: {batch_str}
        각 항목에는 한자(kanji), 읽는 법(furigana), 한국어 의미(means), JLPT 레벨(JLPT)이 포함되어야 합니다.
        JLPT 레벨은 N1, N2, N3, N4, N5, OTHER 중 하나로 꼭 지정해주세요.
        반드시 다음 형식의 JSON 배열로만 응답해주세요:
        [
          {{"kanji": "한자1", "furigana": "읽는법1", "means": "한국어 의미1", "JLPT": "N1"}},
          {{"kanji": "한자2", "furigana": "읽는법2", "means": "한국어 의미2", "JLPT": "N2"}}
        ]
        응답은 JSON 배열만 포함해야하며, 다른 텍스트나 설명은 포함하지 마세요.
        """
        try:
            response = model.generate_content(prompt)
            content = response.text
            clean_text = re.sub(r"```(?:json)?", "", content).strip()
            batch_results = json.loads(clean_text)
            results.extend(batch_results)
            print(f"배치 {i // batch_size + 1} 생성 완료: {len(batch_results)} 항목")
        except Exception as e:
            print(f"AI 데이터 생성 중 오류 발생: {e}. 해당 배치를 건너뜁니다.")
            for kanji in batch:
                results.append({"kanji": kanji, "furigana": "", "means": "정보 없음", "JLPT": "OTHER"})
        
        time.sleep(1)
    return results

def store_new_kanji_in_dynamodb(items):
    """새로 생성된 한자 데이터를 DynamoDB에 저장합니다."""
    if not items:
        return
    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(DYNAMODB_TABLE_NAME)
        with table.batch_writer() as batch:
            for item in items:
                plain_item = {
                    'kanji': item.get('kanji', ''),
                    'furigana': item.get('furigana', ''),
                    'means': item.get('means', ''),
                    'JLPT': item.get('JLPT', 'OTHER')
                }
                batch.put_item(Item=plain_item)
        print(f"✅ {len(items)}개의 새 항목을 DynamoDB에 저장했습니다.")
    except Exception as e:
        print(f"❌ DynamoDB 일괄 저장 실패: {e}")

# =================================================================
# Lambda Handler (메인 실행 함수)
# =================================================================

def lambda_handler(event, context):
    for record in event['Records']:
        book_name_for_error = "Unknown"
        try:
            # 1. SQS 메시지 파싱 및 S3에서 데이터 다운로드
            message = json.loads(record['body'])
            s3_bucket = message['s3_bucket']
            s3_key = message['s3_key']
            print(f"새 작업 수신. 데이터 위치: s3://{s3_bucket}/{s3_key}")

            response = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
            content_string = response['Body'].read().decode('utf-8')
            data_from_s3 = json.loads(content_string)
            
            book_name = data_from_s3['book_name']
            book_name_for_error = os.path.basename(book_name)
            
            # 2. 데이터 중복 제거
            kanji_data_list_with_duplicates = data_from_s3['kanji_data']
            unique_kanji_data = []
            seen_kanji = set()
            for item in kanji_data_list_with_duplicates:
                kanji = item.get('kanji')
                if kanji and kanji not in seen_kanji:
                    unique_kanji_data.append(item)
                    seen_kanji.add(kanji)
            kanji_data_list = unique_kanji_data
            
            kanji_list_to_query = [item['kanji'] for item in kanji_data_list]
            kanji_page_map = {item['kanji']: item['pages'] for item in kanji_data_list}
            print(f"데이터 로드 완료: {book_name}, 중복 제거 후 {len(kanji_list_to_query)}개 한자")

            # 3. DynamoDB 조회, AI 증강, DB 저장을 배치 단위로 반복
            keys_to_process = [{'kanji': {'S': kan}} for kan in kanji_list_to_query]
            batch_size = 100
            all_processed_items = []
            print("데이터 증강 및 저장 작업 시작...")

            for i in range(0, len(keys_to_process), batch_size):
                batch_keys = keys_to_process[i:i + batch_size]
                requested_kanjis = [key['kanji']['S'] for key in batch_keys]
                
                print(f"--- 배치 {i//batch_size + 1} / {(len(keys_to_process) + batch_size - 1)//batch_size} 처리 시작 ---")

                db_response = dynamodb_client.batch_get_item(RequestItems={DYNAMODB_TABLE_NAME: {'Keys': batch_keys}})
                found_items_in_batch = db_response.get('Responses', {}).get(DYNAMODB_TABLE_NAME, [])
                all_processed_items.extend(found_items_in_batch)
                
                found_kanjis_set = {item['kanji']['S'] for item in found_items_in_batch}
                not_found_kanjis_in_batch = [kan for kan in requested_kanjis if kan not in found_kanjis_set]
                print(f"DB 조회: {len(found_items_in_batch)}개 찾음, {len(not_found_kanjis_in_batch)}개 못 찾음")

                if not_found_kanjis_in_batch:
                    ai_generated_items = generate_ai_data(not_found_kanjis_in_batch)
                    if ai_generated_items:
                        store_new_kanji_in_dynamodb(ai_generated_items)
                        for item in ai_generated_items:
                            all_processed_items.append({
                                'kanji': {'S': item.get('kanji', '')}, 'furigana': {'S': item.get('furigana', '')},
                                'means': {'S': item.get('means', '')}, 'JLPT': {'S': item.get('JLPT', 'OTHER')}
                            })
                print(f"--- 배치 {i//batch_size + 1} 처리 완료 ---")

            # 4. 최종 JSON 데이터 생성
            final_details = []
            original_order_map = {item['kanji']: item for item in kanji_data_list}
            sorted_processed_items = sorted(all_processed_items, key=lambda x: list(original_order_map.keys()).index(x['kanji']['S']))

            for idx, data in enumerate(sorted_processed_items, 1):
                kanji = data['kanji']['S']
                page = kanji_page_map.get(kanji, [0])[0]
                final_details.append({
                    'vocabulary_book_order': idx, 'kanji': kanji, 'furigana': data['furigana']['S'],
                    'means': data['means']['S'], 'level': data['JLPT']['S'], 'page': page
                })
            
            final_json_output = {
                'book_name': book_name, 'details': final_details,
                'pages_len': data_from_s3.get('total_pages', 0),
                'max_words': len(final_details)
            }

            # 5. 최종 결과를 S3에 저장
            output_key = f"processed/{book_name_for_error}"
            s3_client.put_object(
                Bucket=S3_RESULTS_BUCKET, Key=output_key,
                Body=json.dumps(final_json_output, ensure_ascii=False, indent=2),
                ContentType='application/json'
            )
            print(f"✅ 처리 완료. 최종 결과 저장: s3://{S3_RESULTS_BUCKET}/{output_key}")

            # 6. Spring에 작업 완료 알림 SQS 메시지 전송
            notification_message = {
                'status': 'complete', 'bookName': book_name_for_error,
                'message': '한자 데이터 처리가 성공적으로 완료되었습니다.'
            }
            sqs_client.send_message(
                QueueUrl=SQS_NOTIFICATION_URL, MessageBody=json.dumps(notification_message)
            )
            print(f"✅ Spring으로 작업 완료 알림 전송: {book_name_for_error}")

        except Exception as e:
            print(f"❌ 에러 발생: {e}")
            try:
                error_message = {'status': 'FAILED_complete', 'bookName': book_name_for_error, 'error': str(e)}
                sqs_client.send_message(
                    QueueUrl=SQS_NOTIFICATION_URL, MessageBody=json.dumps(error_message)
                )
                print(f"💀 Spring으로 작업 실패 알림 전송: {book_name_for_error}")
            except Exception as sqs_e:
                print(f"알림 SQS 전송 실패: {sqs_e}")
            raise e
            
    return {'statusCode': 200, 'body': json.dumps('성공적으로 처리되었습니다.')}