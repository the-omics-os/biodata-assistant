# Email Testing Script

A simple utility to test AgentMail email sending functionality.

## Setup

1. Ensure your `.env` file contains `AGENTMAIL_API_KEY`:
   ```bash
   AGENTMAIL_API_KEY=your_api_key_here
   ```

2. Install dependencies (if not already installed):
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

## Usage

Run the email testing script:

```bash
python backend/test_email.py
```

The script will:

1. **Validate Environment**: Check if `AGENTMAIL_API_KEY` is set in your `.env` file
2. **Collect Email Details**: Prompt you for:
   - Recipient email address (required)
   - From email address (defaults to `test@omics-os.com`)
   - Subject line (defaults to `Test Email from AgentMail`)
   - Message body (multi-line input, press Enter twice to finish)
3. **Preview Email**: Show you the email content before sending
4. **Send Email**: Use AgentMailClient to send via the AgentMail API
5. **Display Results**: Show success/failure with message ID or error details

## Example Session

```
📧 AGENTMAIL EMAIL TESTING UTILITY
Simple script to test email sending functionality

• Uses AgentMail API for email delivery
• Loads configuration from .env file  
• Interactive prompts for recipient and content

✓ Environment validation passed

📝 Email Details
Recipient email address: user@example.com
From email address [test@omics-os.com]: 
Email subject [Test Email from AgentMail]: Hello from AgentMail
Enter your email message (press Enter twice to finish):
This is a test message to verify that our AgentMail integration is working correctly.

Best regards,
Test Script

📋 Email Preview
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                                Email Content                                 ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ From: test@omics-os.com                                                      │
│ To: user@example.com                                                         │
│ Subject: Hello from AgentMail                                                │
│                                                                              │
│ This is a test message to verify that our AgentMail integration is wor...   │
└──────────────────────────────────────────────────────────────────────────────┘

Send this email? [Y/n]: y

Sending email via AgentMail...
From: test@omics-os.com
To: user@example.com
Subject: Hello from AgentMail

✅ Email sent successfully!
Message ID: msg_abc123def456
Thread ID: thread_789xyz321
Status: sent

Response headers received ✓
```

## Features

- **Environment Validation**: Checks for required API key
- **Interactive Input**: User-friendly prompts for all email details
- **Multi-line Message Input**: Enter paragraph breaks naturally
- **Email Preview**: See exactly what will be sent before confirmation
- **Detailed Results**: Shows success/failure with API response details
- **Error Handling**: Graceful handling of API errors and network issues
- **Rich UI**: Beautiful terminal interface with colors and panels

## Troubleshooting

### Missing API Key
```
Environment Issues
AGENTMAIL_API_KEY missing in .env file

Please check your .env file and ensure AGENTMAIL_API_KEY is set.
```
**Solution**: Add `AGENTMAIL_API_KEY=your_key` to your `.env` file.

### API Errors
If you see API errors, check:
- Your AgentMail API key is valid and active
- You have sufficient API credits/quota
- The recipient email address is valid
- Your network connection is stable

### Import Errors
If you get import errors, ensure you're in the correct directory and have installed dependencies:
```bash
cd backend
pip install -r requirements.txt
python test_email.py
```

## Integration Notes

This script uses the same `AgentMailClient` class as the main application, so successful tests here confirm that the email sending functionality in `demo.py` should work correctly.

The script creates an `EmailMessage` object and uses `AgentMailClient.send_email()` method, which is identical to how emails are sent in the production flow.
