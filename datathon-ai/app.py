

import os
from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename
from pathlib import Path
import uuid
from agno.agent import Agent
from agno.media import File
from agno.models.google import Gemini
from agno.db.sqlite import SqliteDb
from dotenv import load_dotenv
from xml.etree import ElementTree as ET
from pathlib import Path
from xml.etree import ElementTree as ET
import re
import io


# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'super-secret-key-123'

# Local file setup
UPLOAD_FOLDER = 'uploads'
PORTFOLIO_FOLDER = 'portfolios'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'doc', 'docx', 'csv', 'xml'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PORTFOLIO_FOLDER'] = PORTFOLIO_FOLDER

# Create necessary directories
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PORTFOLIO_FOLDER, exist_ok=True)

# Predefined portfolio files - these will be created if they don't exist
PORTFOLIO_DATA = {
    'sp500': [
        "AAPL,Apple Inc.",
        "MSFT,Microsoft",
        "AMZN,Amazon",
        "NVDA,Nvidia",
        "GOOGL,Alphabet Inc. (Class A)",
        "TSLA,Tesla Inc.",
        "META,Meta Platforms",
        "BRK.B,Berkshire Hathaway",
        "JPM,JPMorgan Chase",
        "JNJ,Johnson & Johnson"
    ],
    'nasdaq': [
        "AAPL,Apple Inc.",
        "MSFT,Microsoft",
        "AMZN,Amazon",
        "NVDA,Nvidia",
        "GOOGL,Alphabet Inc. (Class A)",
        "META,Meta Platforms",
        "TSLA,Tesla Inc.",
        "AVGO,Broadcom",
        "COST,Costco",
        "ADBE,Adobe Inc."
    ],
    'dowjones': [
        "AAPL,Apple",
        "MSFT,Microsoft",
        "AMZN,Amazon",
        "NVDA,Nvidia",
        "JPM,JPMorgan Chase",
        "JNJ,Johnson & Johnson",
        "V,Visa Inc.",
        "WMT,Walmart",
        "PG,Procter & Gamble",
        "UNH,UnitedHealth Group"
    ]
}

# AI Database - Use session-specific databases
def get_session_db(session_id):
    """Get or create a database for the current session"""
    if not session_id:
        session_id = 'default'
    db_file = f"chat_history_{session_id}.db"
    return SqliteDb(db_file=db_file)

# Google AI Key
os.environ["GOOGLE_API_KEY"] = "AIzaSyCE7Rcv1DI8kVPzs2momYdLtRv_9vO5ybU"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_portfolio_files():
    """Create portfolio CSV files if they don't exist"""
    for portfolio_name, stocks in PORTFOLIO_DATA.items():
        portfolio_path = os.path.join(app.config['PORTFOLIO_FOLDER'], f"{portfolio_name}.csv")
        if not os.path.exists(portfolio_path):
            with open(portfolio_path, 'w') as f:
                f.write("Ticker,Name\n")
                for stock in stocks:
                    f.write(f"{stock}\n")
            print(f"Created portfolio file: {portfolio_path}")

def get_agent(session_id=None):
    """Create our AI agent with session-specific memory"""
    session_db = get_session_db(session_id)
    
    return Agent(
        model=Gemini(id="gemini-2.0-flash-exp"),
        markdown=True,
        add_history_to_context=True,
        db=session_db,
        # Add instructions for financial analysis
        instructions="You are a financial analyst specializing in portfolio impact analysis. Analyze documents for their potential effects on stock portfolios, considering sectors, individual companies, market trends, and risk factors. Provide actionable insights for investors. Use clear section headers (## for main sections, ### for subsections), bullet points, and bold text for important terms."
    )

@app.route('/')
def index():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    # Create portfolio files on startup
    create_portfolio_files()
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files and 'portfolio' not in request.form:
        return jsonify({'error': 'No file selected and no portfolio specified'}), 400
    
    portfolio_type = request.form.get('portfolio')
    
    # Handle portfolio selection
    if portfolio_type:
        if portfolio_type != 'personal-portfolio':
            # Use predefined portfolio
            portfolio_file = os.path.join(app.config['PORTFOLIO_FOLDER'], f"{portfolio_type}.csv")
            if not os.path.exists(portfolio_file):
                # Create the portfolio file if it doesn't exist
                create_portfolio_files()
            
            if not os.path.exists(portfolio_file):
                return jsonify({'error': f'Portfolio {portfolio_type} not available'}), 400
            
            session['portfolio_file'] = portfolio_file
            session['portfolio_type'] = portfolio_type
            session['current_portfolio'] = f"{portfolio_type.upper()} Portfolio"
        else:
            # Personal portfolio - will be handled by file upload
            session['portfolio_type'] = 'personal-portfolio'
            session['current_portfolio'] = 'Personal Portfolio'
    
    # Handle document upload (financial document)
    file = request.files.get('file')
    if file and file.filename != '':
        if file and allowed_file(file.filename):
            try:
                filename = secure_filename(file.filename)
                local_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                # Save file locally
                file.save(local_path)
                
                # Store file info in session
                session['uploaded_file'] = local_path
                session['file_analyzed'] = False
                session['current_filename'] = filename
                
                return jsonify({
                    'success': True, 
                    'filename': filename,
                    'portfolio': portfolio_type,
                    'message': 'File uploaded successfully! Ready for portfolio impact analysis.'
                })
                
            except Exception as e:
                return jsonify({'error': f'Upload failed: {str(e)}'}), 500
        else:
            return jsonify({'error': 'Invalid file type. Please upload: ' + ', '.join(ALLOWED_EXTENSIONS)}), 400
    
    # If only portfolio was selected (no document yet)
    return jsonify({
        'success': True,
        'portfolio': portfolio_type,
        'message': f'{portfolio_type.upper()} portfolio selected. Please upload a document to analyze.'
    })

@app.route('/upload_portfolio', methods=['POST'])
def upload_portfolio():
    """Handle personal portfolio file upload"""
    if 'file' not in request.files:
        return jsonify({'error': 'No portfolio file selected'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No portfolio file selected'}), 400
    
    if file and allowed_file(file.filename):
        try:
            filename = secure_filename(file.filename)
            portfolio_path = os.path.join(app.config['UPLOAD_FOLDER'], f"portfolio_{filename}")
            
            # Save portfolio file
            file.save(portfolio_path)
            
            # Store portfolio info in session
            session['portfolio_file'] = portfolio_path
            session['portfolio_type'] = 'personal-portfolio'
            session['current_portfolio'] = f'Personal Portfolio: {filename}'
            
            return jsonify({
                'success': True, 
                'filename': filename,
                'message': 'Personal portfolio uploaded successfully!'
            })
            
        except Exception as e:
            return jsonify({'error': f'Portfolio upload failed: {str(e)}'}), 500
    
    return jsonify({'error': 'Invalid portfolio file type. Please upload CSV, PDF, or TXT'}), 400





def convert_xml_to_text(xml_path):
    """
    Safely convert an XML file into plain text for analysis.
    Handles namespaces, processing instructions, and malformed tags gracefully.
    """
    try:
        # 1️⃣ Read the raw file (ignore encoding errors)
        with open(xml_path, "r", encoding="utf-8", errors="ignore") as f:
            raw_xml = f.read()

        # 2️⃣ Remove processing instructions like <?I97 ?> and DOCTYPE lines
        cleaned_xml = re.sub(r"<\?.*?\?>", "", raw_xml)
        cleaned_xml = re.sub(r"<!DOCTYPE.*?>", "", cleaned_xml)

        # 3️⃣ Remove problematic namespaces to avoid "unbound prefix" errors
        cleaned_xml = re.sub(r'xmlns(:\w+)?="[^"]+"', "", cleaned_xml)

        # 4️⃣ Try to parse safely
        try:
            tree = ET.parse(io.StringIO(cleaned_xml))
            root = tree.getroot()
            text_parts = [
                elem.text.strip()
                for elem in root.iter()
                if elem.text and elem.text.strip()
            ]
            extracted_text = "\n\n".join(text_parts)
        except ET.ParseError as parse_err:
            print(f"⚠️ XML parse warning for {xml_path}: {parse_err}")
            # fallback: strip tags manually if parser fails
            extracted_text = re.sub(r"<[^>]+>", "", cleaned_xml)

        # 5️⃣ Save to a temporary text file next to the XML
        txt_path = Path(xml_path).with_suffix(".txt")
        txt_path.write_text(extracted_text, encoding="utf-8")

        print(f"✅ XML converted successfully → {txt_path}")
        return str(txt_path)

    except Exception as e:
        print(f"❌ XML conversion failed for {xml_path}: {e}")
        # fallback to the original XML if conversion fails
        return xml_path




@app.route('/summarize', methods=['POST'])
def summarize_file():
    # Check if we have both a document and a portfolio
    if 'uploaded_file' not in session:
        return jsonify({'error': 'No financial document uploaded'}), 400
    
    if 'portfolio_file' not in session and 'portfolio_type' not in session:
        return jsonify({'error': 'No portfolio selected'}), 400
    
    file_path = session.get('uploaded_file')
    portfolio_type = session.get('portfolio_type', 'personal-portfolio')
    
    # For predefined portfolios, we don't need to upload the portfolio file to the AI
    # We just need to tell the AI which portfolio we're analyzing
    user_input = request.json.get('message', '')
    
    try:
        # Create AI agent
        agent = get_agent(session.get('session_id'))
        
        # Only analyze the uploaded financial document
        # The portfolio information is provided in the prompt
        files_to_analyze = []
        
        if file_path and os.path.exists(file_path):
    # If XML, convert to text first
            if file_path.lower().endswith(".xml"):
                print(f"🟣 Converting XML file before analysis: {file_path}")
                file_path = convert_xml_to_text(file_path)

            files_to_analyze.append(File(filepath=Path(file_path)))

        
        # Create context-aware prompt with portfolio information
        portfolio_context = session.get('current_portfolio', 'the selected portfolio')
        
        # For predefined portfolios, include the stock list in the prompt
        portfolio_stocks = ""
        if portfolio_type != 'personal-portfolio' and portfolio_type in PORTFOLIO_DATA:
            portfolio_stocks = f"The {portfolio_type.upper()} portfolio contains stocks like: {', '.join([stock.split(',')[0] for stock in PORTFOLIO_DATA[portfolio_type][:10]])} and others."
        
        prompt = f"""
Analyze the provided financial document and assess its potential impact on {portfolio_context}.

{portfolio_stocks}

Please provide a well-structured analysis with the following sections:

## Key Findings from the Document
- Summarize the main points
- Focus on financial/regulatory implications
- Use bullet points for clarity


## Sector & Company-Specific Impacts Analysis
- Break down by industry sectors (Technology, Healthcare, Financials, Energy, etc.)
- Identify winners and losers in each sector
- Mention specific ticker symbols from the portfolio
- Use **bold** for company names and tickers (e.g., **AAPL**)
- Quantify potential effects where possible
- Provide specific examples

## Overall Portfolio Assessment
- Net expected impact on portfolio value
- Risk level assessment (Low/Medium/High)
- Timeframe considerations (Short-term vs Long-term)
- Portfolio diversification implications

## Disclaimer
- Standard investment disclaimer about consulting financial advisors
- Note that this is analysis, not financial advice
- Market conditions may change rapidly

Please use clear section headers (## for main sections), bullet points, and proper formatting for readability. Focus on actionable insights for portfolio management.

{user_input}
"""
        
        response = agent.run(
            input=prompt,
            files=files_to_analyze,
            stream=False
        )
        
        session['file_analyzed'] = True
        
        return jsonify({
            'success': True,
            'summary': response.content,
            'type': 'analysis'
        })
        
    except Exception as e:
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500

@app.route('/chat', methods=['POST'])
def chat():
    # Check if we have both a document and a portfolio
    if 'uploaded_file' not in session:
        return jsonify({'error': 'Please upload a financial document first!'}), 400
    
    if 'portfolio_file' not in session and 'portfolio_type' not in session:
        return jsonify({'error': 'Please select a portfolio first!'}), 400
    
    user_input = request.json.get('message', '')
    if not user_input:
        return jsonify({'error': 'No message provided'}), 400
    
    try:
        agent = get_agent(session.get('session_id'))
        file_path = session.get('uploaded_file')
        portfolio_context = session.get('current_portfolio', 'the selected portfolio')
        
        # Only analyze the uploaded financial document
        files_to_analyze = []
        
        if file_path and os.path.exists(file_path):
            files_to_analyze.append(File(filepath=Path(file_path)))
        
        # Enhanced prompt with portfolio context
        enhanced_prompt = f"Regarding the document analysis and {portfolio_context}: {user_input}"
        
        response = agent.run(
            input=enhanced_prompt,
            files=files_to_analyze,
            stream=False
        )
        
        return jsonify({
            'success': True,
            'response': response.content,
            'type': 'chat'
        })
        
    except Exception as e:
        return jsonify({'error': f'Chat error: {str(e)}'}), 500

@app.route('/predefined_prompt', methods=['POST'])
def predefined_prompt():
    # Check if we have both a document and a portfolio
    if 'uploaded_file' not in session:
        return jsonify({'error': 'Please upload a financial document first!'}), 400
    
    if 'portfolio_file' not in session and 'portfolio_type' not in session:
        return jsonify({'error': 'Please select a portfolio first!'}), 400
    
    prompt_type = request.json.get('type')
    portfolio_context = session.get('current_portfolio', 'the selected portfolio')
    portfolio_type = session.get('portfolio_type', 'personal-portfolio')
    
    # For predefined portfolios, include stock information
    portfolio_stocks = ""
    if portfolio_type != 'personal-portfolio' and portfolio_type in PORTFOLIO_DATA:
        portfolio_stocks = f"The {portfolio_type.upper()} portfolio contains stocks like: {', '.join([stock.split(',')[0] for stock in PORTFOLIO_DATA[portfolio_type][:10]])} and others."
    
    prompts = {
        'historical': f"## Historical Context & Comparisons\n\nProvide historical context and comparisons for how similar documents/events have impacted {portfolio_context}. {portfolio_stocks}\n\n- Analyze patterns from past market reactions\n- Compare with similar regulatory/legislative events\n- Identify lessons learned from historical precedents\n- Timeframe analysis (short-term vs long-term effects)\n\nPlease use clear section headers and bullet points.",
        'forecast': f"## Future Projections & Forecasts\n\nBased on the document analysis, provide forecasts and future projections for {portfolio_context}. {portfolio_stocks}\n\n- Key indicators to watch\n- Potential market movements and timing\n- Sector-specific outlook\n- Risk factors in the forecast\n- Recommended monitoring timeline\n\nPlease structure with clear sections, actionable insights.", 
        'solutions': f"## Risk Mitigation & Solutions\n\nAnalyze risks identified in the document and suggest specific risk mitigation strategies for {portfolio_context}. {portfolio_stocks}\n\n- Portfolio adjustment recommendations\n- Hedging strategies\n- Diversification opportunities\n- Monitoring and alert triggers\n- Contingency planning\n- Apply Buy-Hold-Sell analysis for any stocks or sectors that are at risk after taking all the preceding into account.\n\n- Remember, be consise and use bullet points."
    }
    
    if prompt_type not in prompts:
        return jsonify({'error': 'Invalid prompt type'}), 400
    
    try:
        agent = get_agent(session.get('session_id'))
        file_path = session.get('uploaded_file')
        
        # Only analyze the uploaded financial document
        files_to_analyze = []
        
        if file_path and os.path.exists(file_path):
            files_to_analyze.append(File(filepath=Path(file_path)))
        
        response = agent.run(
            input=prompts[prompt_type],
            files=files_to_analyze,
            stream=False
        )
        
        return jsonify({
            'success': True,
            'response': response.content,
            'type': 'predefined'
        })
        
    except Exception as e:
        return jsonify({'error': f'Prompt error: {str(e)}'}), 500

@app.route('/new_session', methods=['POST'])
def new_session():
    """Create a new session for uploading a different file"""
    session.clear()
    session['session_id'] = str(uuid.uuid4())
    return jsonify({'success': True, 'message': 'New session created'})

if __name__ == '__main__':
    # Create portfolio files on startup
    create_portfolio_files()
    app.run(debug=True, host='0.0.0.0', port=5000)
