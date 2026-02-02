import os
import json
import boto3

# 1. 초기화 (핸들러 함수 밖에서 실행)
# 최종 결과 JSON 파일이 저장된 S3 버킷 이름을 환경 변수에서 가져옵니다.
S3_RESULTS_BUCKET = os.getenv('S3_RESULTS_BUCKET')
s3_client = boto3.client('s3')

def lambda_handler(event, context):
    """
    API Gateway로부터 GET 요청을 받아 S3에 저장된 JSON 파일을 반환합니다.
    """
    print(f"Received event: {event}")

    try:
        # 2. API Gateway 경로 파라미터에서 파일 이름(book_name) 추출
        # API Gateway 리소스 경로가 /kanji-data/{book_name} 형태일 때,
        # {book_name}에 해당하는 값을 여기서 꺼낼 수 있습니다.
        path_params = event.get('pathParameters', {})
        book_name = path_params.get('book_name')

        if not book_name:
            # book_name이 없는 경우, 잘못된 요청으로 처리
            return {
                'statusCode': 400,
                'body': json.dumps({'error': '파일 이름이 지정되지 않았습니다.'})
            }

        # 3. S3 객체 키(전체 경로) 생성
        # 이 경로는 프로세싱 Lambda가 파일을 저장할 때 사용한 규칙과 정확히 일치해야 합니다.
        object_key = f"processed/{book_name}"
        print(f"S3에서 파일 찾는 중: s3://{S3_RESULTS_BUCKET}/{object_key}")

        # 4. S3에서 해당 JSON 파일 가져오기
        response = s3_client.get_object(
            Bucket=S3_RESULTS_BUCKET,
            Key=object_key
        )
        
        # 파일 내용을 문자열로 읽어옵니다.
        content_string = response['Body'].read().decode('utf-8')

        # 5. 성공 응답을 API Gateway 형식에 맞게 반환
        return {
            'statusCode': 200,
            'headers': {
                # 일본어 등 다국어 문자가 깨지지 않도록 charset=utf-8 설정
                'Content-Type': 'application/json; charset=utf-8'
            },
            'body': content_string # S3에서 읽은 JSON 문자열을 그대로 전달
        }

    except s3_client.exceptions.NoSuchKey:
        # 파일이 S3에 없는 경우 404 Not Found 에러 반환
        return {
            'statusCode': 404,
            'body': json.dumps({'error': '요청한 데이터를 찾을 수 없습니다.'}, ensure_ascii=False)
        }
    except Exception as e:
        # 기타 에러 발생 시 500 Internal Server Error 반환
        print(f"Error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': '서버 내부 오류가 발생했습니다.'}, ensure_ascii=False)
        }