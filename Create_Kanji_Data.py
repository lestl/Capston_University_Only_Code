import pypdf
import re
from flask import Flask, jsonify
import boto3
import json
from urllib.parse import unquote_plus
from boto3.dynamodb.conditions import Key, Attr
import os
import threading
import time
import google.generativeai as genai
from dotenv import load_dotenv
from pathlib import Path
from collections import defaultdict

class App_Runner:
    def __init__(self):
        load_dotenv()
        self.app = Flask(__name__)
        self.sqs_jsonMessage = os.getenv('SQS_JSON_URL')
        self.kanji_instance = None  # 초기에는 없음

        # SQS 대기 스레드 시작
        self.start_sqs_listener()

        @self.app.route('/api/kanji/all', methods=['GET'])
        def kanji_all():
            if self.kanji_instance:
                return jsonify(self.kanji_instance.all_data)
            return jsonify({"message": "아직 데이터 없음"})

        @self.app.route('/')
        def hello_world():
            return 'hi'

    def start_sqs_listener(self):
        listener_thread = threading.Thread(target=self.sqs_listener_loop)
        listener_thread.daemon = True
        listener_thread.start()

    def sqs_listener_loop(self):
        while True:
            print("📥 SQS 메시지 감지 대기 중...")
            new_kanji_instance = Create_Kanji_Data()
            self.kanji_instance = new_kanji_instance
            if hasattr(new_kanji_instance, 'all_data') and new_kanji_instance.all_data:
                print("✅ 새로운 한자 데이터 처리 완료")
                try:
                    sqs = boto3.client('sqs', region_name=os.getenv('AWS_REGION'))
                    sqs.send_message(
                        QueueUrl=self.sqs_jsonMessage,
                        MessageBody='complete'  # 데이터 처리 완료 메시지
                    )
                    print("📤 SQS로 JSON 메시지 전송 완료")
                except Exception as e:
                    print(f"[ERROR] SQS 전송 실패: {e}")
                    
    def run(self):
        self.app.run(host='0.0.0.0', port=5000)
# class App_Runner:
#     def __init__(self):
#         load_dotenv() # .env 파일 로드
#         self.app = Flask(__name__) # flask 앱 생성하여 JSON 시각화
#         self.sqs_jsonMessage = os.getenv('SQS_JSON_URL')
#         self.kanji_instance = Create_Kanji_Data()  # 초기 데이터 생성
#         self.last_refresh_time = time.time()
#         # 60초마다 데이터 갱신 타이머 시작 (30초에서 60초로 변경)
#         self.start_refresh_timer()
        
#         # flask 라우트 설정 (JSON 시각화) 
#         @self.app.route('/api/kanji/all', methods=['GET'])
#         def kanji_all():
#             data = jsonify(self.kanji_instance.all_data)
#             return data  # JSON 응답

#         # 그냥 루트 서버
#         @self.app.route('/')
#         def hello_world():
#             return 'hi'
    
#     # SQS 메시지를 60초마다 재갱신하여 새 데이터를 처리
#     def refresh_data(self):
#         """60초마다 데이터를 갱신하는 함수"""
#         current_time = time.time()
#         if current_time - self.last_refresh_time > 60:
#             print("60초가 지나 데이터를 갱신합니다...")
#             # 이전 PDF 파일 삭제
#             if hasattr(self.kanji_instance, 'pdf_path'):
#                 try:
#                     if os.path.exists(self.kanji_instance.pdf_path):
#                         os.remove(self.kanji_instance.pdf_path)
#                         print(f"이전 PDF 파일 삭제: {self.kanji_instance.pdf_path}")
#                 except Exception as e:
#                     print(f"파일 삭제 중 오류: {e}")
            
#             # 새 데이터 생성
#             self.kanji_instance = Create_Kanji_Data()
#             self.last_refresh_time = current_time
            
#             # 갱신된 후에만 SQS 메시지 전송 (매번 하지 않음)
#             if hasattr(self.kanji_instance, 'all_data') and self.kanji_instance.all_data:
#                 self.sqs.send_message(
#                     QueueUrl=self.sqs_jsonMessage,
#                     MessageBody=json.dumps(self.kanji_instance.all_data)
#                 )
#                 print("갱신된 데이터를 SQS에 전송했습니다.")
        
#         # 다음 타이머 설정
#         self.start_refresh_timer()
    
#     def start_refresh_timer(self):
#         """60초 후에 데이터 갱신 타이머 설정"""
#         refresh_timer = threading.Timer(60, self.refresh_data)
#         refresh_timer.daemon = True  # 메인 스레드가 종료되면 같이 종료
#         refresh_timer.start()
    
#     def run(self):
#         self.app.run(host='0.0.0.0', port=5000)
    
# 전체적인 한자 데이터 생성 및 처리 클래스
class Create_Kanji_Data():
    def __init__(self):
        self.page_num = 0
        self.sqs = boto3.client('sqs', region_name=os.getenv('AWS_REGION'))
        self.sns = boto3.client('sns', region_name=os.getenv('AWS_REGION'))
        self.s3 = boto3.client('s3', region_name=os.getenv('AWS_REGION'))
        self.response = None
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        self.model = genai.GenerativeModel("gemini-1.5-flash")
        self.dynamodb = boto3.client('dynamodb', region_name=os.getenv('AWS_REGION'))
        self.sns_messageARN = os.getenv('SNS_ARN')
        self.sqs_queueURL = os.getenv('SQS_PDF_URL')
        self.sqs_jsonMessage = os.getenv('SQS_JSON_URL')
        self.pdf_path = self.poll_sqs_and_process()
        self.all_data = {
            'book_name': self.pdf_path,
            'details': [],
            'pages_len': '',
            'max_words': 0
        }
        
        # PDF 내용과 페이지 정보를 한 번에 추출 (최적화)
        self.kanji_data, self.kanji_page_map = self.extract_kanji_data_with_pages(self.pdf_path)
        self.find_data_kanji(self.kanji_data)  # 바로 실행
    
    def process_pdf_from_s3(self, bucket, key):
        # 저장 폴더가 없으면 생성
        os.makedirs("s3PDF", exist_ok=True)
        local_path = f"s3PDF/{key}"

        # S3에서 PDF 다운로드
        self.s3.download_file(bucket, key, local_path)
        print(f"PDF 다운로드 완료: {local_path}")
        
        return local_path

    def poll_sqs_and_process(self):
        print("SQS 폴링 시작...")

        while True:
            self.response = self.sqs.receive_message(  # SQS 메시지 수신
                QueueUrl=self.sqs_queueURL, 
                MaxNumberOfMessages=1,
                WaitTimeSeconds=10
            )

            messages = self.response.get("Messages", [])  # SQS 메시지 가져오기
            if not messages:
                continue

            for message in messages:
                body = json.loads(message['Body'])
                s3_event = json.loads(body['Message'])
                # sns를 통해 sqs로 전달된 메시지에서 s3 이벤트 정보 추출
                print(s3_event)
                
                bucket = None
                key = None
                
                for record in s3_event.get('Records', []):
                    # S3 이벤트에서 버킷과 객체 키 추출
                    bucket = record.get('s3', {}).get('bucket', {}).get('name')
                    key = record.get('s3', {}).get('object', {}).get('key')
                    if key:
                        key = unquote_plus(key)
                        print(f"추출된 키: {key}")
                
                if bucket and key:
                    print(f"🆕 새로운 PDF 감지: s3://{bucket}/{key}")
                    local_path = self.process_pdf_from_s3(bucket, key)

                    # SQS메시지 삭제
                    self.sqs.delete_message(
                        QueueUrl=self.sqs_queueURL,
                        ReceiptHandle=message['ReceiptHandle']
                    )
                    print("🗑️ 메시지 삭제 완료")
                    return local_path
                else:
                    print("유효한 S3 이벤트가 없습니다.")
            
    def extract_kanji_data_with_pages(self, pdf_path):
        """PDF에서 한자 데이터와 해당 한자가 있는 페이지 정보를 함께 추출"""
        try:
            print("PDF 추출 시작")
            reader = pypdf.PdfReader(pdf_path)
        except Exception as e:
            print(f"PDF 파일 열기 실패: {e}")
            return [], {}
            
        # 페이지 수 저장
        self.all_data['pages_len'] = len(reader.pages)
        
        # 한자와 페이지 매핑을 위한 딕셔너리
        kanji_page_map = defaultdict(list)
        unique_kanji = set()
        
        pattern = r'[\u4E00-\u9FFF]+(?:[\u3040-\u309F]+[\u4E00-\u9FFF]*)*'
        
        # 한 번의 순회로 한자와 페이지 정보 수집
        for page_num, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if not page_text:
                continue
                
            # 페이지에서 한자 추출
            kanjis_in_page = re.findall(pattern, page_text)
            
            # 한자와 페이지 매핑
            for kanji in kanjis_in_page:
                kanji = kanji.strip()
                if kanji:
                    unique_kanji.add(kanji)
                    kanji_page_map[kanji].append(page_num + 1)
        
        kanji_list = list(unique_kanji)
        print(f'{len(kanji_list)}개의 한자 추출 완료')
        self.all_data['max_words'] = len(kanji_list)  # 최대 단어 수 저장
        
        return kanji_list, kanji_page_map

    def generate_kanji_data_batch(self, kanji_list, batch_size=10):
        """여러 한자를 동시에 처리하여 AI로 데이터 생성"""
        if not kanji_list:
            return []
            
        results = []
        
        # 배치 크기로 나누어 처리
        for i in range(0, len(kanji_list), batch_size):
            batch = kanji_list[i:i+batch_size]
            batch_str = ", ".join(batch)
            
            print(f"AI 데이터 생성 시작: 배치 {i//batch_size + 1} ({len(batch)} 한자)")
            
            # 개선된 프롬프트: 여러 한자를 한 번에 처리
            prompt = f"""다음 일본 한자에 대한 정보를 JSON 배열 형태로 생성해주세요: {batch_str}
            
            각 항목에는 한자(kanji), 읽는 법(furigana), 한국어 의미(means), JLPT 레벨(JLPT)이 포함되어야 합니다.
            JLPT 레벨은 N1, N2, N3, N4, N5 중 하나로 꼭 지정해주세요.
            반드시 다음 형식의 JSON 배열로 응답해주세요:
            
            [
              {{
                "kanji": "한자1",
                "furigana": "읽는법1",
                "means": "한국어 의미1",
                "JLPT": "N1/N2/N3/N4/N5 중 하나"
              }},
              {{
                "kanji": "한자2",
                "furigana": "읽는법2",
                "means": "한국어 의미2",
                "JLPT": "N1/N2/N3/N4/N5 중 하나"
              }},
              ...
            ]
            
            응답은 JSON 배열만 포함해야하며, 다른 텍스트나 설명은 포함하지 마세요.
            """
            
            try:
                response = self.model.generate_content(prompt)
                content = response.text
                # ```json 태그 제거 및 JSON 변환
                clean_text = re.sub(r"```(?:json)?", "", content).strip()
                batch_results = json.loads(clean_text)
                
                # 배치 결과를 전체 결과에 추가
                results.extend(batch_results)
                print(f"배치 {i//batch_size + 1} 생성 완료: {len(batch_results)} 항목")
            except Exception as e:
                print(f"AI 데이터 생성 중 오류 발생: {e}")
                # 오류 발생 시 개별 처리로 폴백
                for kanji in batch:
                    try:
                        single_prompt = f"""다음 일본 한자에 대한 정보를 JSON 형태로 생성해주세요: {kanji}
                        
                        한자(kanji), 읽는 법(furigana), 한국어 의미(means), JLPT 레벨(JLPT)이 포함되어야 합니다.
                        다음 형식의 JSON 객체로만 응답해주세요:
                        
                        {{
                          "kanji": "한자",
                          "furigana": "읽는법",
                          "means": "한국어 의미",
                          "JLPT": "N1/N2/N3/N4/N5 중 하나"
                        }}
                        """
                        single_response = self.model.generate_content(single_prompt)
                        single_content = single_response.text
                        clean_single = re.sub(r"```(?:json)?", "", single_content).strip()
                        single_result = json.loads(clean_single)
                        results.append(single_result)
                        print(f"개별 처리 완료: {kanji}")
                    except Exception as inner_e:
                        print(f"개별 한자 처리 중 오류: {inner_e}")
                        # 최소한의 결과라도 제공
                        results.append({
                            "kanji": kanji,
                            "furigana": "",
                            "means": "정보 없음",
                            "JLPT": "OTHER"  # 기본값
                        })
        
        return results

    def store_in_dynamodb_batch(self, items):
        """여러 항목을 DynamoDB에 일괄 저장"""
        if not items:
            return
            
        # DynamoDB batch_write_item은 최대 25개 항목으로 제한
        batch_size = 25
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i+batch_size]
            request_items = []
            
            for item in batch:
                request_items.append({
                    'PutRequest': {
                        'Item': {
                            'kanji': {'S': item['kanji']},
                            'furigana': {'S': item['furigana']},
                            'means': {'S': item['means']},
                            'JLPT': {'S': item['JLPT']}
                        }
                    }
                })
            
            try:
                response = self.dynamodb.batch_write_item(
                    RequestItems={
                        os.getenv('DYNAMODB_TABLE_NAME'): request_items
                    }
                )
                
                # 실패한 항목이 있으면 재시도
                unprocessed = response.get('UnprocessedItems', {}).get(os.getenv('DYNAMODB_TABLE_NAME'), [])
                if unprocessed:
                    print(f"{len(unprocessed)}개 항목 처리 실패, 재시도 필요")
                    # 여기에 재시도 로직 추가 가능
            except Exception as e:
                print(f"[ERROR] DynamoDB 일괄 저장 실패: {e}")

    def find_data_kanji(self, kanji_data):
        print("데이터 검색 및 JSON 변환 시작")
        
        # 중복 제거 및 공백 처리
        kanji_data = list(set([kan.strip() for kan in kanji_data if isinstance(kan, str) and kan.strip()]))
        
        # DynamoDB 키 형식으로 변환
        keys = [{'kanji': {'S': kan}} for kan in kanji_data]
        
        # 배치 크기 설정 (최대 100개)
        batch_size = 100
        all_found_items = []
        not_found_kanjis = []
        
        # 배치로 DynamoDB 조회
        for i in range(0, len(keys), batch_size):
            batch_keys = keys[i:i+batch_size]
            requested_kanjis = [key['kanji']['S'] for key in batch_keys]
            
            try:
                response = self.dynamodb.batch_get_item(RequestItems={
                    os.getenv('DYNAMODB_TABLE_NAME'): {
                        'Keys': batch_keys,
                        'ProjectionExpression': 'kanji, furigana, JLPT, means'
                    }
                })
                
                # 찾은 항목 처리
                items = response.get('Responses', {}).get(os.getenv('DYNAMODB_TABLE_NAME'), [])
                found_kanjis = [item['kanji']['S'] for item in items]
                
                # 찾은 항목 저장
                all_found_items.extend(items)
                
                # 못 찾은 항목 식별
                batch_not_found = list(set(requested_kanjis) - set(found_kanjis))
                not_found_kanjis.extend(batch_not_found)
                
                print(f"배치 {i//batch_size + 1}: {len(found_kanjis)}개 찾음, {len(batch_not_found)}개 못 찾음")
                
            except Exception as e:
                print(f"[ERROR] DynamoDB 요청 실패: {e}")
                # 오류 발생 시 이 배치의 모든 한자를 못 찾은 것으로 처리
                not_found_kanjis.extend(requested_kanjis)
        
        # 못 찾은 한자에 대해 AI 모델로 데이터 생성 (배치 처리)
        if not_found_kanjis:
            print(f"{len(not_found_kanjis)}개의 한자를 AI로 생성합니다")
            ai_generated_items = self.generate_kanji_data_batch(not_found_kanjis)
            
            # 생성된 데이터를 DynamoDB에 저장
            self.store_in_dynamodb_batch(ai_generated_items)
            
            # AI 생성 데이터를 DynamoDB 형식으로 변환
            ai_db_items = []
            for item in ai_generated_items:
                ai_db_items.append({
                    'kanji': {'S': item['kanji']},
                    'furigana': {'S': item['furigana']},
                    'means': {'S': item['means']},
                    'JLPT': {'S': item['JLPT']}
                })
            
            # 찾은 항목과 AI 생성 항목 합치기
            all_found_items.extend(ai_db_items)
        
        # 모든 데이터를 JSON으로 변환
        for idx, data in enumerate(all_found_items, 1):
            kanji = data['kanji']['S']
            
            # 페이지 정보 가져오기 (미리 저장한 맵에서)
            page = self.kanji_page_map.get(kanji, [0])[0]  # 첫 번째 발견 페이지
            
            json_data = {
                'vocabulary_book_order': idx,
                'kanji': kanji,
                'furigana': data['furigana']['S'],
                'means': data['means']['S'],
                'level': data['JLPT']['S'],
                'page': page
            }
            
            self.all_data['details'].append(json_data)
        
        print(f"전체 {len(self.all_data['details'])}개의 한자 데이터 처리 완료")
        
app_runner = App_Runner()  # Flask 앱 초기화 및 타이머 시작
app = app_runner.app  # Flask 앱 인스턴스 가져오기
if __name__ == '__main__':
    app_runner.run()  # Flask 서버 실행
    
    