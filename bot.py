import discord
from discord.ext import commands
import asyncio
import aiohttp
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, quote
import re
import logging
from pathlib import Path
import hashlib

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ResearchBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        # Remove privileged intent requirement
        super().__init__(command_prefix='!research ', intents=intents)
        
        # Initialize session for HTTP requests
        self.session = None
        
        # Project storage
        self.base_dir = Path("research_projects")
        self.base_dir.mkdir(exist_ok=True)
    
    async def on_ready(self):
        """Initialize HTTP session when bot starts"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        print(f'🤖 {self.user} has logged in to Discord!')
        print(f'📊 Bot is ready in {len(self.guilds)} guilds')
        
        # Debug: List all guilds
        if len(self.guilds) == 0:
            print("⚠️  WARNING: Bot is not in any servers!")
            print("🔗 Make sure you've invited the bot using the OAuth2 URL")
        else:
            print("🌐 Connected to servers:")
            for guild in self.guilds:
                print(f"   - {guild.name} (ID: {guild.id})")
        
        print("✅ Bot startup complete!")
        
    async def close(self):
        """Clean up when bot shuts down"""
        if self.session:
            await self.session.close()
        await super().close()

class PubMedSearcher:
    """Handler for PubMed searches and paper fetching"""
    
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
    
    async def search_papers(self, keywords: str, start_year: int = None, 
                          end_year: int = None, max_results: int = 10) -> List[Dict]:
        """Search PubMed for papers matching criteria"""
        try:
            # Construct search query
            search_term = keywords
            if start_year and end_year:
                search_term += f" AND {start_year}[PDAT]:{end_year}[PDAT]"
            
            # Search for PMIDs
            search_params = {
                'db': 'pubmed',
                'term': search_term,
                'retmax': max_results,
                'retmode': 'xml',
                'sort': 'relevance'
            }
            
            search_url = f"{self.BASE_URL}/esearch.fcgi?" + urlencode(search_params)
            
            async with self.session.get(search_url) as response:
                if response.status != 200:
                    logger.error(f"Search failed: {response.status}")
                    return []
                
                xml_data = await response.text()
                root = ET.fromstring(xml_data)
                
                # Extract PMIDs
                pmids = []
                for id_elem in root.findall('.//Id'):
                    pmids.append(id_elem.text)
                
                if not pmids:
                    return []
                
                # Fetch detailed info for each PMID
                return await self._fetch_paper_details(pmids)
                
        except Exception as e:
            logger.error(f"Error searching PubMed: {e}")
            return []
    
    async def _fetch_paper_details(self, pmids: List[str]) -> List[Dict]:
        """Fetch detailed paper information"""
        try:
            fetch_params = {
                'db': 'pubmed',
                'id': ','.join(pmids),
                'retmode': 'xml',
                'rettype': 'abstract'
            }
            
            fetch_url = f"{self.BASE_URL}/efetch.fcgi?" + urlencode(fetch_params)
            
            async with self.session.get(fetch_url) as response:
                xml_data = await response.text()
                root = ET.fromstring(xml_data)
                
                papers = []
                for article in root.findall('.//PubmedArticle'):
                    paper_info = self._extract_paper_info(article)
                    if paper_info:
                        papers.append(paper_info)
                
                return papers
                
        except Exception as e:
            logger.error(f"Error fetching paper details: {e}")
            return []
    
    def _extract_paper_info(self, article) -> Optional[Dict]:
        """Extract paper information from XML"""
        try:
            # Basic info
            title_elem = article.find('.//ArticleTitle')
            title = title_elem.text if title_elem is not None else "No title"
            
            # Authors
            authors = []
            for author in article.findall('.//Author'):
                last_name = author.find('LastName')
                first_name = author.find('ForeName')
                if last_name is not None:
                    name = last_name.text
                    if first_name is not None:
                        name = f"{first_name.text} {name}"
                    authors.append(name)
            
            # Abstract
            abstract_elem = article.find('.//AbstractText')
            abstract = abstract_elem.text if abstract_elem is not None else "No abstract available"
            
            # DOI
            doi_elem = article.find('.//ELocationID[@EIdType="doi"]')
            doi = doi_elem.text if doi_elem is not None else None
            
            # PMID
            pmid_elem = article.find('.//PMID')
            pmid = pmid_elem.text if pmid_elem is not None else None
            
            # Publication year
            year_elem = article.find('.//PubDate/Year')
            year = year_elem.text if year_elem is not None else "Unknown"
            
            return {
                'title': title,
                'authors': authors,
                'abstract': abstract,
                'doi': doi,
                'pmid': pmid,
                'year': year,
                'pdf_url': f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmid}/pdf/" if pmid else None
            }
            
        except Exception as e:
            logger.error(f"Error extracting paper info: {e}")
            return None

class ProjectManager:
    """Manages research project folders and metadata"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
    
    def create_project(self, query: str, user_id: str) -> Path:
        """Create a new project folder"""
        # Generate project ID from query and timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        query_hash = hashlib.md5(query.encode()).hexdigest()[:8]
        project_name = f"project_{timestamp}_{query_hash}"
        
        project_dir = self.base_dir / project_name
        project_dir.mkdir(exist_ok=True)
        
        # Create subdirectories
        (project_dir / "papers").mkdir(exist_ok=True)
        (project_dir / "datasets").mkdir(exist_ok=True)
        (project_dir / "summaries").mkdir(exist_ok=True)
        
        # Create metadata file
        metadata = {
            'project_id': project_name,
            'query': query,
            'user_id': user_id,
            'created_at': datetime.now().isoformat(),
            'papers_found': 0,
            'papers_downloaded': 0,
            'status': 'created'
        }
        
        with open(project_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
        
        return project_dir
    
    def update_metadata(self, project_dir: Path, updates: Dict):
        """Update project metadata"""
        metadata_file = project_dir / "metadata.json"
        
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
        else:
            metadata = {}
        
        metadata.update(updates)
        metadata['updated_at'] = datetime.now().isoformat()
        
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

# Initialize bot
bot = ResearchBot()

@bot.command(name='search', help='Search for papers: !research search <keywords> [year_start] [year_end] [max_results]')
async def search_papers(ctx, *, args: str):
    """Search for research papers"""
    
    # Parse arguments
    parts = args.split()
    if len(parts) < 1:
        await ctx.send("❌ Please provide search keywords")
        return
    
    # Extract optional parameters
    keywords = []
    start_year = None
    end_year = None
    max_results = 10
    
    for part in parts:
        if part.isdigit() and len(part) == 4:  # Year
            year = int(part)
            if 1900 <= year <= 2030:
                if start_year is None:
                    start_year = year
                else:
                    end_year = year
        elif part.isdigit():  # Max results
            max_results = min(int(part), 50)  # Cap at 50
        else:
            keywords.append(part)
    
    if not keywords:
        await ctx.send("❌ Please provide search keywords")
        return
    
    keywords_str = ' '.join(keywords)
    
    # Send initial message
    embed = discord.Embed(
        title="🔍 Searching for Papers",
        description=f"Keywords: **{keywords_str}**\nYears: {start_year or 'Any'} - {end_year or 'Any'}\nMax results: {max_results}",
        color=0x3498db
    )
    message = await ctx.send(embed=embed)
    
    try:
        # Create project
        project_manager = ProjectManager(bot.base_dir)
        project_dir = project_manager.create_project(keywords_str, str(ctx.author.id))
        
        # Search papers
        searcher = PubMedSearcher(bot.session)
        papers = await searcher.search_papers(keywords_str, start_year, end_year, max_results)
        
        if not papers:
            embed = discord.Embed(
                title="❌ No Papers Found",
                description=f"No papers found for: **{keywords_str}**",
                color=0xe74c3c
            )
            await message.edit(embed=embed)
            return
        
        # Update project metadata
        project_manager.update_metadata(project_dir, {
            'papers_found': len(papers),
            'status': 'search_complete'
        })
        
        # Save papers to JSON
        with open(project_dir / "papers_metadata.json", 'w') as f:
            json.dump(papers, f, indent=2)
        
        # Create summary embed
        embed = discord.Embed(
            title="✅ Papers Found",
            description=f"Found **{len(papers)}** papers for: **{keywords_str}**",
            color=0x27ae60
        )
        
        # Add paper previews
        for i, paper in enumerate(papers[:5]):  # Show first 5
            authors_str = ", ".join(paper['authors'][:3])
            if len(paper['authors']) > 3:
                authors_str += f" +{len(paper['authors'])-3} more"
            
            embed.add_field(
                name=f"📄 {paper['title'][:100]}{'...' if len(paper['title']) > 100 else ''}",
                value=f"**Authors:** {authors_str}\n**Year:** {paper['year']}\n**PMID:** {paper['pmid'] or 'N/A'}",
                inline=False
            )
        
        if len(papers) > 5:
            embed.add_field(
                name="📋 Additional Papers",
                value=f"+ {len(papers) - 5} more papers found",
                inline=False
            )
        
        embed.add_field(
            name="📁 Project",
            value=f"Saved to: `{project_dir.name}`\nUse `!research download {project_dir.name}` to download PDFs",
            inline=False
        )
        
        await message.edit(embed=embed)
        
    except Exception as e:
        logger.error(f"Error in search command: {e}")
        embed = discord.Embed(
            title="❌ Search Error",
            description=f"An error occurred while searching: {str(e)}",
            color=0xe74c3c
        )
        await message.edit(embed=embed)

@bot.command(name='download', help='Download PDFs for a project: !research download <project_name>')
async def download_papers(ctx, project_name: str):
    """Download PDFs for papers in a project"""
    
    project_dir = bot.base_dir / project_name
    
    if not project_dir.exists():
        await ctx.send(f"❌ Project `{project_name}` not found")
        return
    
    papers_file = project_dir / "papers_metadata.json"
    if not papers_file.exists():
        await ctx.send(f"❌ No papers metadata found in project `{project_name}`")
        return
    
    # Load papers
    with open(papers_file, 'r') as f:
        papers = json.load(f)
    
    embed = discord.Embed(
        title="📥 Downloading Papers",
        description=f"Attempting to download {len(papers)} papers...",
        color=0x3498db
    )
    message = await ctx.send(embed=embed)
    
    downloaded = 0
    failed = 0
    
    try:
        for i, paper in enumerate(papers):
            if paper.get('doi'):
                # Try to download via various sources
                success = await _try_download_paper(bot.session, paper, project_dir / "papers")
                if success:
                    downloaded += 1
                else:
                    failed += 1
            else:
                failed += 1
            
            # Update progress every 5 papers
            if (i + 1) % 5 == 0 or i == len(papers) - 1:
                embed = discord.Embed(
                    title="📥 Downloading Papers",
                    description=f"Progress: {i+1}/{len(papers)}\n✅ Downloaded: {downloaded}\n❌ Failed: {failed}",
                    color=0x3498db
                )
                await message.edit(embed=embed)
        
        # Update project metadata
        project_manager = ProjectManager(bot.base_dir)
        project_manager.update_metadata(project_dir, {
            'papers_downloaded': downloaded,
            'status': 'download_complete'
        })
        
        # Final result
        embed = discord.Embed(
            title="✅ Download Complete",
            description=f"Downloaded: **{downloaded}** papers\nFailed: **{failed}** papers\nSaved to: `{project_dir / 'papers'}`",
            color=0x27ae60 if downloaded > 0 else 0xe74c3c
        )
        await message.edit(embed=embed)
        
    except Exception as e:
        logger.error(f"Error in download command: {e}")
        embed = discord.Embed(
            title="❌ Download Error",
            description=f"An error occurred while downloading: {str(e)}",
            color=0xe74c3c
        )
        await message.edit(embed=embed)

async def _try_download_paper(session: aiohttp.ClientSession, paper: Dict, download_dir: Path) -> bool:
    """Try to download a paper PDF from various sources"""
    
    download_dir.mkdir(exist_ok=True)
    
    # Generate filename
    safe_title = re.sub(r'[^\w\s-]', '', paper['title'])[:50]
    filename = f"{paper['pmid'] or 'unknown'}_{safe_title}.pdf"
    filepath = download_dir / filename
    
    # Skip if already exists
    if filepath.exists():
        return True
    
    # Try different sources
    urls_to_try = []
    
    if paper.get('doi'):
        # Try Unpaywall (free access)
        urls_to_try.append(f"https://api.unpaywall.org/v2/{paper['doi']}?email=research@example.com")
    
    if paper.get('pmid'):
        # Try PMC
        urls_to_try.append(f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{paper['pmid']}/pdf/")
    
    for url in urls_to_try:
        try:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '')
                    
                    if 'application/pdf' in content_type:
                        # Direct PDF download
                        with open(filepath, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        return True
                    elif 'application/json' in content_type:
                        # Unpaywall API response
                        data = await response.json()
                        if data.get('is_oa') and data.get('best_oa_location'):
                            pdf_url = data['best_oa_location'].get('url_for_pdf')
                            if pdf_url:
                                return await _download_pdf_direct(session, pdf_url, filepath)
        except Exception as e:
            logger.debug(f"Failed to download from {url}: {e}")
            continue
    
    return False

async def _download_pdf_direct(session: aiohttp.ClientSession, url: str, filepath: Path) -> bool:
    """Download PDF directly from URL"""
    try:
        async with session.get(url, timeout=30) as response:
            if response.status == 200:
                with open(filepath, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                return True
    except Exception as e:
        logger.debug(f"Failed direct PDF download: {e}")
    
    return False

@bot.command(name='projects', help='List all projects')
async def list_projects(ctx):
    """List all research projects"""
    
    projects = []
    for project_dir in bot.base_dir.iterdir():
        if project_dir.is_dir():
            metadata_file = project_dir / "metadata.json"
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                projects.append((project_dir.name, metadata))
    
    if not projects:
        await ctx.send("📁 No projects found")
        return
    
    embed = discord.Embed(
        title="📁 Research Projects",
        description=f"Found {len(projects)} project(s)",
        color=0x3498db
    )
    
    for project_name, metadata in projects[-10:]:  # Show last 10
        created_at = datetime.fromisoformat(metadata['created_at']).strftime("%Y-%m-%d %H:%M")
        embed.add_field(
            name=f"📂 {project_name}",
            value=f"**Query:** {metadata.get('query', 'N/A')}\n**Created:** {created_at}\n**Papers:** {metadata.get('papers_found', 0)} found, {metadata.get('papers_downloaded', 0)} downloaded\n**Status:** {metadata.get('status', 'unknown')}",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='info', help='Show available commands')
async def info_command(ctx):
    """Show help information"""
    
    embed = discord.Embed(
        title="🤖 Research Bot Commands",
        description="A Discord bot to help with research paper discovery and management",
        color=0x9b59b6
    )
    
    embed.add_field(
        name="🔍 Search",
        value="`!research search <keywords> [start_year] [end_year] [max_results]`\nSearch for papers on PubMed",
        inline=False
    )
    
    embed.add_field(
        name="📥 Download",
        value="`!research download <project_name>`\nDownload PDFs for papers in a project",
        inline=False
    )
    
    embed.add_field(
        name="📁 Projects",
        value="`!research projects`\nList all research projects",
        inline=False
    )
    
    embed.add_field(
        name="❓ Info",
        value="`!research info`\nShow this help message",
        inline=False
    )
    
    embed.add_field(
        name="📝 Examples",
        value="`!research search morbidostat gentamicin 2023 2024 10`\n`!research search CRISPR gene editing`\n`!research download project_20241213_abc123def`",
        inline=False
    )
    
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Command not found. Use `!research info` to see available commands.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error.param.name}")
    else:
        logger.error(f"Command error: {error}")
        await ctx.send(f"❌ An error occurred: {str(error)}")

if __name__ == "__main__":
    # Replace with your bot token
    TOKEN = "MTQxNjUxNzE3MTU3OTk4MTk3Ng.GZ-x6k.G-0g8UWGZfTSdPnTKIEDIEzHygNnolDpFxUD88"
    
    if TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("❌ Please set your Discord bot token in the TOKEN variable")
        exit(1)
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Invalid bot token. Please check your Discord bot token.")
    except Exception as e:
        print(f"❌ Error starting bot: {e}")