# send_email.py
import boto3
from botocore.exceptions import ClientError

def send_email():
    ses_client = boto3.client('ses', region_name='us-east-1')  # specify your region
    sender = 'info@mediablackout.ai'
    recipient = 'info@mediablackout.ai'
    subject = 'Test Email from AWS SES'
    body_text = 'This is a test email sent through AWS SES using boto3.'
    body_html = """<html>
    <head></head>
    <body>
      <h1>Hello from AWS SES</h1>
      <p>This is a test email sent through AWS SES using boto3.</p>
    </body>
    </html>"""
    charset = 'UTF-8'
    try:
        response = ses_client.send_email(
            Source=sender,
            Destination={
                'ToAddresses': [recipient],
            },
            Message={
                'Subject': {
                    'Data': subject,
                    'Charset': charset
                },
                'Body': {
                    'Text': {
                        'Data': body_text,
                        'Charset': charset
                    },
                    'Html': {
                        'Data': body_html,
                        'Charset': charset
                    }
                }
            }
        )
        print("Email sent! Message ID: {}".format(response['MessageId']))
    except ClientError as e:
        print(e.response['Error']['Message'])

if __name__ == "__main__":
    send_email()
