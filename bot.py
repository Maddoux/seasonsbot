import discord
from discord.ext import commands
from discord import app_commands
import os
import re
import asyncio
from dotenv import load_dotenv
from typing import Optional, List
from database import DatabaseManager
from license_manager import LicenseManager
from violations import VIOLATIONS, get_punishment_action, calculate_points

# Load environment variables
load_dotenv()

def is_valid_url(url: str) -> bool:
    """Check if a string is a valid URL"""
    if not url or not isinstance(url, str):
        return False
    
    url = url.strip()
    
    # Basic URL pattern - be lenient
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return bool(url_pattern.match(url))

def format_clip_text(clips: List[str], use_newlines: bool = False) -> str:
    """Format clips with fallback for non-URL content"""
    if not clips:
        return ""
    
    # Filter out empty clips
    valid_clips = [clip for clip in clips if clip and clip.strip()]
    if not valid_clips:
        return ""
    
    # Count URL and text clips separately
    url_clips = [clip for clip in valid_clips if is_valid_url(clip)]
    text_clips = [clip for clip in valid_clips if not is_valid_url(clip)]
    
    formatted_clips = []
    
    # Handle URL clips
    for i, clip in enumerate(url_clips):
        if len(url_clips) == 1:
            # Single URL - no numbering needed
            formatted_clips.append(f"[Clip]({clip})")
        else:
            # Multiple URLs - use numbering
            formatted_clips.append(f"[Clip {i+1}]({clip})")
    
    # Handle text clips
    for i, clip in enumerate(text_clips):
        if len(valid_clips) == 1:
            # Single item overall - no numbering needed
            formatted_clips.append(clip)
        else:
            # Multiple items - use simple numbering
            formatted_clips.append(f"{i+1}) {clip}")
    
    separator = "\n" if use_newlines else ", "
    return separator.join(formatted_clips)

class WarningsView(discord.ui.View):
    def __init__(self, warnings: List[dict], user: discord.User, bot_instance):
        super().__init__(timeout=300)
        self.warnings = warnings
        self.user = user
        self.bot = bot_instance
        self.current_page = 0
        self.per_page = 5
        self.max_pages = (len(warnings) - 1) // self.per_page + 1 if warnings else 1
        
        # Update button states
        self.update_buttons()
    
    def update_buttons(self):
        """Update button states based on current page"""
        # Clear existing buttons
        self.clear_items()
        
        # Add navigation buttons if needed
        if self.max_pages > 1:
            # Previous button
            prev_button = discord.ui.Button(
                label="Previous",
                style=discord.ButtonStyle.secondary,
                disabled=self.current_page == 0
            )
            prev_button.callback = self.previous_page
            self.add_item(prev_button)
            
            # Page indicator
            page_button = discord.ui.Button(
                label=f"Page {self.current_page + 1}/{self.max_pages}",
                style=discord.ButtonStyle.gray,
                disabled=True
            )
            self.add_item(page_button)
            
            # Next button
            next_button = discord.ui.Button(
                label="Next",
                style=discord.ButtonStyle.secondary,
                disabled=self.current_page >= self.max_pages - 1
            )
            next_button.callback = self.next_page
            self.add_item(next_button)
    
    async def previous_page(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            embed = await self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    async def next_page(self, interaction: discord.Interaction):
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            self.update_buttons()
            embed = await self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    async def create_embed(self) -> discord.Embed:
        """Create embed for current page"""
        if not self.warnings:
            embed = discord.Embed(
                title=f"No warnings found for {self.user.display_name}",
                color=discord.Color.green()
            )
            return embed
        
        embed = discord.Embed(
            title=f"Warnings for {self.user.display_name}",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow()
        )
        
        # Calculate range for current page
        start_idx = self.current_page * self.per_page
        end_idx = min(start_idx + self.per_page, len(self.warnings))
        page_warnings = self.warnings[start_idx:end_idx]
        
        for i, warning in enumerate(page_warnings):
            moderator = self.bot.get_user(warning['moderator_id'])
            if moderator:
                moderator_name = moderator.mention
            else:
                # If user not in cache, create mention directly
                moderator_name = f"<@{warning['moderator_id']}>"
            
            # Check if warning was removed
            status = " (REMOVED)" if warning.get("removed", False) else ""
            
            warning_title = f"{start_idx + i + 1}. {warning['violation_type']} ({warning['points']} pts){status}"
            warning_value = f"By: {moderator_name}\nDate: <t:{int(discord.utils.parse_time(warning['timestamp']).timestamp())}:R>\nID: `{warning['id']}`"
            
            # Add clips/evidence if available
            if warning.get('clips') and len(warning['clips']) > 0:
                clips_text = format_clip_text(warning['clips'])
                if clips_text:
                    warning_value += f"\nEvidence: {clips_text}"
            
            # Add removal info if applicable
            if warning.get("removed", False):
                removed_by = self.bot.get_user(warning.get("removed_by"))
                removed_by_mention = removed_by.mention if removed_by else f"<@{warning.get('removed_by')}>"
                warning_value += f"\nRemoved by: {removed_by_mention}"
            
            embed.add_field(
                name=warning_title,
                value=warning_value,
                inline=False
            )
        
        # Add summary info
        from database import DatabaseManager
        db = DatabaseManager()
        total_points = await db.get_user_points(self.user.id)
        ban_status = get_punishment_action(total_points)
        
        embed.add_field(
            name="Summary",
            value=f"Points: {total_points} | {ban_status}",
            inline=False
        )
        
        if self.max_pages > 1:
            embed.set_footer(text=f"Page {self.current_page + 1} of {self.max_pages} • Showing {len(page_warnings)} of {len(self.warnings)} warnings")
        else:
            embed.set_footer(text=f"Showing all {len(self.warnings)} warnings")
        
        embed.set_thumbnail(url=self.user.display_avatar.url)
        return embed

class ViolationSelect(discord.ui.Select):
    def __init__(self, user: discord.User, clips: List[str], moderator: discord.Member):
        self.target_user = user
        self.clips = clips
        self.moderator = moderator
        
        options = []
        for violation_type in VIOLATIONS.keys():
            options.append(discord.SelectOption(
                label=violation_type,
                description=VIOLATIONS[violation_type]["description"][:100],
                value=violation_type
            ))
        
        super().__init__(
            placeholder="Select violation type(s)...", 
            options=options,
            min_values=1,
            max_values=len(options)  # Allow multiple selections
        )
    
    async def callback(self, interaction: discord.Interaction):
        selected_violations = self.values
        
        # Get database instance
        db = DatabaseManager()
        
        total_points_added = 0
        warning_details = []
        
        # Process each selected violation
        for violation_type in selected_violations:
            violation_data = VIOLATIONS[violation_type]
            
            # Count previous violations of the same type
            user_warnings = await db.get_user_warnings(self.target_user.id)
            previous_violations = sum(1 for w in user_warnings if w["violation_type"] == violation_type)
            
            # Calculate points
            points = calculate_points(violation_type, previous_violations)
            total_points_added += points
            
            # Add warning to database
            warning = await db.add_warning(
                user_id=self.target_user.id,
                moderator_id=self.moderator.id,
                violation_type=violation_type,
                points=points,
                clips=self.clips,
                reason=violation_data["description"]
            )
            
            warning_details.append({
                "type": violation_type,
                "points": points,
                "warning": warning
            })
        
        # Get updated total points
        total_points = await db.get_user_points(self.target_user.id)
        action = get_punishment_action(total_points)
        
        # Create response embed
        embed = discord.Embed(
            title="Warning(s) Issued",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="User", value=f"{self.target_user.mention if hasattr(self.target_user, 'mention') else self.target_user.display_name} ({self.target_user.id})", inline=True)
        embed.add_field(name="Violations", value=str(len(selected_violations)), inline=True)
        embed.add_field(name="Points Added", value=str(total_points_added), inline=True)
        embed.add_field(name="Total Points", value=str(total_points), inline=True)
        embed.add_field(name="Action Required", value=action, inline=True)
        embed.add_field(name="Moderator", value=self.moderator.mention, inline=True)
        
        # Add violation details
        violation_text = ""
        for detail in warning_details:
            violation_text += f"• {detail['type']} ({detail['points']} pts)\n"
        # Ensure violation text doesn't exceed Discord's 1024 character limit
        if len(violation_text) > 1024:
            violation_text = violation_text[:1000] + "... (truncated)"
        embed.add_field(name="Violation Details", value=violation_text, inline=False)
        
        if self.clips:
            clip_text = format_clip_text(self.clips, use_newlines=True)
            # Ensure clip text doesn't exceed Discord's 1024 character limit for embed fields
            if len(clip_text) > 1024:
                clip_text = clip_text[:1000] + "... (truncated)"
            embed.add_field(name="Evidence", value=clip_text, inline=False)
        
        warning_ids = [detail['warning']['id'] for detail in warning_details]
        embed.set_footer(text=f"Warning IDs: {', '.join(warning_ids)}")
        
        await interaction.response.edit_message(embed=embed, view=None)
        
        # Log to warning log channel
        await self.log_warnings(interaction, warning_details, total_points, action)
        
        # Send DM to user
        dm_success = await self.send_user_dm(selected_violations, total_points_added, total_points, action)
        
        # Show DM failure notification if needed
        if not dm_success:
            dm_fail_embed = discord.Embed(
                title="DM Failed",
                description=f"Could not send DM to {self.target_user.mention}",
                color=discord.Color.yellow()
            )
            await interaction.followup.send(embed=dm_fail_embed, ephemeral=True)
        
        # Check if ban is required
        if total_points >= 15:  # If ban is required
            await self.create_ban_request(interaction, total_points, action, warning_details)
    
    async def log_warnings(self, interaction: discord.Interaction, warning_details: List[dict], total_points: int, action: str):
        """Log warnings to the warning log channel"""
        try:
            warning_log_channel_id = int(os.getenv('WARNING_LOG_CHANNEL_ID', '0'))
            if warning_log_channel_id == 0:
                return
                
            warning_log_channel = interaction.guild.get_channel(warning_log_channel_id)
            if not warning_log_channel:
                return
            
            # Get license info
            license_manager = LicenseManager()
            license_info = await license_manager.get_user_license(self.target_user.id)
            
            embed = discord.Embed(
                title="Warning Log",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="User", value=f"{self.target_user.mention if hasattr(self.target_user, 'mention') else self.target_user.display_name} ({self.target_user.id})", inline=True)
            embed.add_field(name="Moderator", value=f"{self.moderator.mention} ({self.moderator})", inline=True)
            embed.add_field(name="Total Points", value=str(total_points), inline=True)
            
            # Add license info
            if license_info:
                embed.add_field(name="License", value=f"`{license_info['license']}`", inline=True)
            else:
                embed.add_field(name="License", value="Not assigned", inline=True)
            
            embed.add_field(name="Action Required", value=action, inline=True)
            
            # Add violation details
            violation_text = ""
            total_points_added = 0
            for detail in warning_details:
                violation_text += f"• {detail['type']} ({detail['points']} pts)\n"
                total_points_added += detail['points']
            # Ensure violation text doesn't exceed Discord's 1024 character limit
            if len(violation_text) > 1024:
                violation_text = violation_text[:1000] + "... (truncated)"
            embed.add_field(name="Violations", value=violation_text, inline=False)
            embed.add_field(name="Points Added", value=str(total_points_added), inline=True)
            
            if self.clips:
                clip_text = format_clip_text(self.clips, use_newlines=True)
                # Ensure clip text doesn't exceed Discord's 1024 character limit
                if len(clip_text) > 1024:
                    clip_text = clip_text[:1000] + "... (truncated)"
                embed.add_field(name="Evidence", value=clip_text, inline=False)
            
            embed.set_thumbnail(url=self.target_user.display_avatar.url)
            
            # Add warning IDs to footer
            warning_ids = [detail['warning']['id'] for detail in warning_details]
            embed.set_footer(text=f"Warning IDs: {', '.join(warning_ids)}")
            
            await warning_log_channel.send(embed=embed)
        except Exception as e:
            print(f"Error logging warning: {e}")
    
    async def send_user_dm(self, selected_violations: List[str], points_added: int, total_points: int, action: str) -> bool:
        """Send DM notification to the warned user"""
        try:
            dm_embed = discord.Embed(
                title="You have received warning(s)",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            
            # Add violation details
            violation_text = ""
            for violation_type in selected_violations:
                violation_data = VIOLATIONS[violation_type]
                violation_text += f"• {violation_type}: {violation_data['description']}\n"
            
            # Ensure violation text doesn't exceed Discord's 1024 character limit
            if len(violation_text) > 1024:
                violation_text = violation_text[:1000] + "... (truncated)"
            
            dm_embed.add_field(name="Violations", value=violation_text, inline=False)
            dm_embed.add_field(name="Points Added", value=str(points_added), inline=True)
            dm_embed.add_field(name="Total Points", value=str(total_points), inline=True)
            dm_embed.add_field(name="Current Status", value=action, inline=True)
            
            # Add clips/evidence if available
            if self.clips:
                clip_text = format_clip_text(self.clips, use_newlines=True)
                # Ensure clip text doesn't exceed Discord's 1024 character limit
                if len(clip_text) > 1024:
                    clip_text = clip_text[:1000] + "... (truncated)"
                dm_embed.add_field(name="Evidence", value=clip_text, inline=False)
            
            if action != "Written Warning":
                dm_embed.add_field(name="Action Required", value=f"**{action}**", inline=False)
                dm_embed.add_field(name="Note", value="Please contact staff if you believe this is in error.", inline=False)
            
            await self.target_user.send(embed=dm_embed)
            print(f"Successfully sent DM to {self.target_user}")
            return True
        except discord.Forbidden:
            print(f"Could not send DM to {self.target_user} - DMs disabled")
            return False
        except discord.HTTPException as e:
            print(f"HTTP error sending DM to {self.target_user}: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error sending DM to {self.target_user}: {e}")
            return False
    
    async def create_ban_request(self, interaction: discord.Interaction, total_points: int, action: str, warning_details: List[dict] = None):
        """Create a ban request in the designated channel"""
        ban_channel_id = int(os.getenv('BAN_REQUEST_CHANNEL_ID'))
        ban_channel = interaction.guild.get_channel(ban_channel_id)
        
        if not ban_channel:
            return
        
        # Store warning details for footer
        self.warning_details = warning_details
        
        # Get license info
        license_manager = LicenseManager()
        license_info = await license_manager.get_user_license(self.target_user.id)
        
        embed = discord.Embed(
            title="Ban Request",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="User", value=f"{self.target_user.mention} ({self.target_user})", inline=True)
        embed.add_field(name="Total Points", value=str(total_points), inline=True)
        embed.add_field(name="Required Action", value=action, inline=True)
        embed.add_field(name="Requested by", value=self.moderator.mention, inline=True)
        
        # Add license info if available
        if license_info:
            embed.add_field(name="License", value=f"`{license_info['license']}`", inline=True)
        else:
            embed.add_field(name="License", value="Not assigned", inline=True)
        
        embed.set_thumbnail(url=self.target_user.display_avatar.url)
        
        # Add warning IDs to footer for ban request
        if hasattr(self, 'warning_details') and self.warning_details:
            warning_ids = [detail['warning']['id'] for detail in self.warning_details]
            embed.set_footer(text=f"Triggered by Warning IDs: {', '.join(warning_ids)}")
        
        view = BanRequestView(self.target_user.id, total_points, action, warning_details)
        message = await ban_channel.send(embed=embed, view=view)
        
        # Save ban request to database
        db = DatabaseManager()
        await db.add_ban_request(self.target_user.id, total_points, action, message.id)

class BanRequestView(discord.ui.View):
    def __init__(self, user_id: int, total_points: int, action: str, warning_details: List[dict] = None):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.total_points = total_points
        self.action = action
        self.warning_details = warning_details
    
    @discord.ui.button(label="Complete Ban", style=discord.ButtonStyle.red)
    async def complete_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user has permission
        moderator_roles = [int(role_id) for role_id in os.getenv('MODERATOR_ROLES', '').split(',') if role_id]
        user_role_ids = [role.id for role in interaction.user.roles]
        
        if not any(role_id in user_role_ids for role_id in moderator_roles):
            await interaction.response.send_message("You don't have permission to complete ban requests.", ephemeral=True)
            return
        
        # Mark as completed in database
        db = DatabaseManager()
        await db.complete_ban_request(interaction.message.id, interaction.user.id)
        
        # Send to completed bans channel
        completed_channel_id = int(os.getenv('BAN_COMPLETED_CHANNEL_ID'))
        completed_channel = interaction.guild.get_channel(completed_channel_id)
        
        user = interaction.guild.get_member(self.user_id)
        if not user:
            try:
                user = await interaction.guild.fetch_member(self.user_id)
            except:
                user = None
        
        # Get license info
        license_manager = LicenseManager()
        license_info = await license_manager.get_user_license(self.user_id)
        
        embed = discord.Embed(
            title="Ban Completed",
            color=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="User", value=f"<@{self.user_id}>" + (f" ({user})" if user else ""), inline=True)
        embed.add_field(name="Total Points", value=str(self.total_points), inline=True)
        embed.add_field(name="Action", value=self.action, inline=True)
        embed.add_field(name="Completed by", value=interaction.user.mention, inline=True)
        
        # Add license info
        if license_info:
            embed.add_field(name="License", value=f"`{license_info['license']}`", inline=True)
        else:
            embed.add_field(name="License", value="Not assigned", inline=True)
        
        if user:
            embed.set_thumbnail(url=user.display_avatar.url)
        
        # Add warning IDs to footer if available
        if self.warning_details:
            warning_ids = [detail['warning']['id'] for detail in self.warning_details]
            embed.set_footer(text=f"Triggered by Warning IDs: {', '.join(warning_ids)}")
        
        if completed_channel:
            await completed_channel.send(embed=embed)
        
        # Update original message
        original_embed = interaction.message.embeds[0]
        original_embed.color = discord.Color.dark_red()
        original_embed.add_field(name="Status", value=f"Completed by {interaction.user.mention}", inline=False)
        
        await interaction.response.edit_message(embed=original_embed, view=None)
        
        # Send DM to banned user
        dm_success = False
        if user:
            try:
                dm_embed = discord.Embed(
                    title="You have been banned",
                    color=discord.Color.dark_red(),
                    timestamp=discord.utils.utcnow()
                )
                dm_embed.add_field(name="Server", value=interaction.guild.name, inline=False)
                dm_embed.add_field(name="Total Points", value=str(self.total_points), inline=True)
                dm_embed.add_field(name="Ban Duration", value=self.action, inline=True)
                dm_embed.add_field(name="Appeal", value="Contact staff if you believe this is in error.", inline=False)
                
                await user.send(embed=dm_embed)
                print(f"Successfully sent ban DM to {user}")
                dm_success = True
            except discord.Forbidden:
                print(f"Could not send ban DM to {user} - DMs disabled")
            except discord.HTTPException as e:
                print(f"HTTP error sending ban DM to {user}: {e}")
            except Exception as e:
                print(f"Unexpected error sending ban DM to {user}: {e}")
        
        # Show DM failure notification if needed
        if user and not dm_success and completed_channel:
            dm_fail_embed = discord.Embed(
                title="⚠️ DM Failed",
                description=f"Could not send ban notification DM to <@{self.user_id}>",
                color=discord.Color.yellow()
            )
            await completed_channel.send(embed=dm_fail_embed)

class WarningView(discord.ui.View):
    def __init__(self, user: discord.User, clips: List[str], moderator: discord.Member):
        super().__init__(timeout=300)
        self.add_item(ViolationSelect(user, clips, moderator))

class SeasonsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(command_prefix='!', intents=intents)
    
    async def setup_hook(self):
        """Setup hook that runs after login but before on_ready"""
        pass
    
    async def on_ready(self):
        print(f'{self.user} has logged in!')
        print(f'Bot is in {len(self.guilds)} guilds')
        
        # List all guilds the bot is in - should only be Seasons RP
        seasons_guild_found = False
        print("Guilds:")
        for guild in self.guilds:
            print(f"  - {guild.name} (ID: {guild.id})")
            if guild.id == 1365988649665036288:
                seasons_guild_found = True
                print(f"    ✅ Seasons RP guild found!")
        
        if not seasons_guild_found:
            print("⚠️  WARNING: Bot is not in Seasons RP guild!")
        
        # Wait a moment to ensure all commands are loaded
        await asyncio.sleep(2)
        
        # Now sync commands after all are loaded
        try:
            # Clear any existing global commands to avoid conflicts
            self.tree.clear_commands(guild=None)
            
            # Check if we're in the target guild
            guild_id = 1365988649665036288  # Seasons RP
            target_guild = self.get_guild(guild_id)
            
            if target_guild:
                # We're in the guild, sync directly to guild only
                synced = await self.tree.sync(guild=target_guild)
                print(f"✅ Successfully synced {len(synced)} commands to guild {guild_id}")
                print(f"Commands: {[cmd.name for cmd in synced]}")
            else:
                # Bot is not in the guild - give clear instructions
                print(f"❌ ERROR: Bot is not in guild {guild_id} (Seasons RP)")
                print("🔧 SOLUTION: Invite the bot to the Discord server using this URL:")
                print(f"   https://discord.com/api/oauth2/authorize?client_id=1398273706890887260&permissions=277025507328&scope=bot%20applications.commands")
                print("⚠️  Commands will NOT work until the bot is properly invited to the guild!")
                return
            
        except Exception as e:
            print(f"❌ Failed to sync commands: {e}")
            import traceback
            traceback.print_exc()
            
            # Only try guild sync as fallback
            try:
                print("Attempting fallback guild sync...")
                guild = discord.Object(id=1365988649665036288)
                synced_guild = await self.tree.sync(guild=guild)
                print(f"Fallback guild sync: {len(synced_guild)} commands")
            except Exception as fallback_error:
                print(f"❌ Guild sync failed: {fallback_error}")
                print("🔧 Make sure the bot is invited to the guild with proper permissions!")
                import traceback
                traceback.print_exc()
        
        # Show command tree info
        global_commands = [cmd.name for cmd in self.tree.get_commands(guild=None)]
        print(f"Global commands: {', '.join(global_commands) if global_commands else 'None'}")
        
        # Check guild-specific commands
        if seasons_guild_found:
            guild = discord.utils.get(self.guilds, id=1365988649665036288)
            if guild:
                guild_commands = [cmd.name for cmd in self.tree.get_commands(guild=guild)]
                print(f"Guild commands: {', '.join(guild_commands) if guild_commands else 'None'}")
        
        all_commands = [cmd.name for cmd in self.tree.get_commands()]
        print(f"All available commands: {', '.join(all_commands)}")
        
        print("Bot is ready and commands should be available!")
    
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handle application command errors"""
        print(f"App command error in {interaction.command.name if interaction.command else 'unknown'}: {error}")
        
        if isinstance(error, app_commands.CommandNotFound):
            print(f"Command not found: {interaction.command}")
        elif isinstance(error, app_commands.MissingPermissions):
            print(f"Missing permissions for {interaction.user}")
        else:
            print(f"Unexpected error type: {type(error)}")
        
        # Try to respond if we haven't already
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"An error occurred: {str(error)}", 
                    ephemeral=True
                )
        except:
            pass
    
    async def on_error(self, event_method: str, *args, **kwargs):
        """Handle general bot errors"""
        print(f"Bot error in {event_method}: {args}")

# Create bot instance and register commands
bot = SeasonsBot()

@bot.tree.command(name="warn", description="Warn a user for rule violations")
@app_commands.describe(
    user="The user to warn",
    clip1="First evidence clip (required)",
    clip2="Second evidence clip (optional)",
    clip3="Third evidence clip (optional)",
    clip4="Fourth evidence clip (optional)",
    clip5="Fifth evidence clip (optional)"
)
async def warn_command(
    interaction: discord.Interaction,
    user: discord.User,
    clip1: str,
    clip2: Optional[str] = None,
    clip3: Optional[str] = None,
    clip4: Optional[str] = None,
    clip5: Optional[str] = None
):
    target_user = user
    
    # Collect clips
    clips = [clip for clip in [clip1, clip2, clip3, clip4, clip5] if clip]
    
    embed = discord.Embed(
        title="Issue Warning",
        description=f"Select a violation type for {target_user.mention if hasattr(target_user, 'mention') else f'**{target_user.display_name}**'}",
        color=discord.Color.blue()
    )
    embed.add_field(name="User", value=f"{target_user.mention if hasattr(target_user, 'mention') else target_user.display_name} ({target_user.id})", inline=True)
    embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
    embed.add_field(name="Evidence Clips", value=str(len(clips)), inline=True)
    
    view = WarningView(target_user, clips, interaction.user)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def resolve_user(interaction: discord.Interaction, user_input: str) -> Optional[discord.User]:
    """Resolve a user from string input (ID, username, mention, etc.)"""
    try:
        # Try to parse as user ID (remove mention formatting if present)
        user_id_str = user_input.strip('<@!>')
        if user_id_str.isdigit():
            user_id = int(user_id_str)
            
            # Try to get as member first (if they're in the server)
            member = interaction.guild.get_member(user_id)
            if member:
                return member
            
            # Try to fetch as user (even if not in server)
            try:
                user = await interaction.client.fetch_user(user_id)
                return user
            except discord.NotFound:
                pass
        
        # Try to find by username in the server
        if interaction.guild:
            for member in interaction.guild.members:
                if (member.name.lower() == user_input.lower() or 
                    member.display_name.lower() == user_input.lower() or
                    (member.global_name and member.global_name.lower() == user_input.lower())):
                    return member
        
        # If all else fails, show error
        embed = discord.Embed(
            title="User Not Found",
            description=f"Could not find user: `{user_input}`\n\nTry using:\n• User ID (e.g., `123456789012345678`)\n• Username (e.g., `username`)\n• Mention (e.g., `@username`)",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return None
        
    except ValueError:
        embed = discord.Embed(
            title="Invalid User Input",
            description=f"Invalid user format: `{user_input}`\n\nTry using:\n• User ID (e.g., `123456789012345678`)\n• Username (e.g., `username`)\n• Mention (e.g., `@username`)",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return None

@bot.tree.command(name="points", description="Check a user's current points")
@app_commands.describe(user="The user to check points for")
async def points_command(interaction: discord.Interaction, user: discord.User):
    target_user = user
    
    db = DatabaseManager()
    total_points = await db.get_user_points(target_user.id)
    warnings = await db.get_user_warnings(target_user.id)
    
    embed = discord.Embed(
        title=f"Points for {target_user.display_name}",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="Total Points", value=str(total_points), inline=True)
    embed.add_field(name="Active Warnings", value=str(len(warnings)), inline=True)
    embed.add_field(name="Current Status", value=get_punishment_action(total_points), inline=True)
    
    if warnings:
        warning_text = ""
        for warning in warnings[:5]:  # Show last 5 warnings
            warning_text += f"• {warning['violation_type']} ({warning['points']} pts)\n"
        if len(warnings) > 5:
            warning_text += f"... and {len(warnings) - 5} more"
        # Ensure warning text doesn't exceed Discord's 1024 character limit
        if len(warning_text) > 1024:
            warning_text = warning_text[:1000] + "... (truncated)"
        embed.add_field(name="Recent Warnings", value=warning_text, inline=False)
    
    embed.set_thumbnail(url=target_user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="warnings", description="View detailed warnings for a user")
@app_commands.describe(user="The user to check warnings for")
async def warnings_command(interaction: discord.Interaction, user: discord.User):
    target_user = user
    
    db = DatabaseManager()
    # Get all warnings including removed ones for complete history
    all_warnings = await db.find_warnings_by_user(target_user.id, limit=100)  # Get up to 100 warnings
    
    view = WarningsView(all_warnings, target_user, bot)
    embed = await view.create_embed()
    
    # Only add view if there are multiple pages
    if view.max_pages > 1:
        await interaction.response.send_message(embed=embed, view=view)
    else:
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="remove", description="Remove warnings or all warnings for a user")
@app_commands.describe(
    user="The user to remove warnings from",
    warning_id="Specific warning ID to remove (optional - removes all if not specified)",
    reason="Reason for removal"
)
async def remove_command(
    interaction: discord.Interaction,
    user: discord.User,
    warning_id: Optional[str] = None,
    reason: Optional[str] = "No reason provided"
):
    # Check if user has permission (same as moderator roles for ban requests)
    moderator_roles = [int(role_id) for role_id in os.getenv('MODERATOR_ROLES', '').split(',') if role_id]
    user_role_ids = [role.id for role in interaction.user.roles]
    
    if not any(role_id in user_role_ids for role_id in moderator_roles):
        await interaction.response.send_message("You don't have permission to remove warnings.", ephemeral=True)
        return
    
    target_user = user
    
    db = DatabaseManager()
    
    if warning_id:
        # Remove specific warning
        success = await db.remove_warning(warning_id, interaction.user.id, reason)
        if success:
            embed = discord.Embed(
                title="Warning Removed",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Warning ID", value=warning_id, inline=True)
            embed.add_field(name="Removed by", value=interaction.user.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            
            # Log removal to warning log channel
            await log_warning_removal(interaction, target_user, warning_id, reason)
        else:
            embed = discord.Embed(
                title="Warning Not Found",
                description=f"Warning ID `{warning_id}` not found.",
                color=discord.Color.red()
            )
    else:
        # Remove all warnings for user
        removed_count = await db.remove_user_warnings(target_user.id, interaction.user.id, reason)
        
        embed = discord.Embed(
            title="Warnings Removed",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="User", value=f"{target_user.display_name} ({target_user.id})", inline=True)
        embed.add_field(name="Warnings Removed", value=str(removed_count), inline=True)
        embed.add_field(name="Removed by", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        
        if removed_count > 0:
            # Log removal to warning log channel
            await log_warning_removal(interaction, target_user, f"All warnings ({removed_count})", reason)
    
    # Get updated points
    updated_points = await db.get_user_points(target_user.id)
    embed.add_field(name="New Point Total", value=str(updated_points), inline=True)
    embed.add_field(name="New Status", value=get_punishment_action(updated_points), inline=True)
    
    embed.set_thumbnail(url=target_user.display_avatar.url)
    await interaction.response.send_message(embed=embed)
    
    # Send DM to user about warning removal
    dm_success = False
    try:
        dm_embed = discord.Embed(
            title="Warning(s) Removed",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        dm_embed.add_field(name="Server", value=interaction.guild.name, inline=False)
        if warning_id:
            dm_embed.add_field(name="Warning Removed", value=f"ID: {warning_id}", inline=True)
        else:
            dm_embed.add_field(name="Warnings Removed", value=f"{removed_count} warning(s)", inline=True)
        dm_embed.add_field(name="Reason", value=reason, inline=False)
        dm_embed.add_field(name="New Point Total", value=str(updated_points), inline=True)
        dm_embed.add_field(name="New Status", value=get_punishment_action(updated_points), inline=True)
        
        await target_user.send(embed=dm_embed)
        print(f"Successfully sent warning removal DM to {target_user}")
        dm_success = True
    except discord.Forbidden:
        print(f"Could not send warning removal DM to {target_user} - DMs disabled")
    except Exception as e:
        print(f"Error sending warning removal DM to {target_user}: {e}")
    
    # Show DM failure notification if needed
    if not dm_success:
        dm_fail_embed = discord.Embed(
            title="⚠️ DM Failed",
            description=f"Could not send removal notification DM to {target_user.mention}",
            color=discord.Color.yellow()
        )
        await interaction.followup.send(embed=dm_fail_embed, ephemeral=True)

async def log_warning_removal(interaction: discord.Interaction, user: discord.User, warning_info: str, reason: str):
    """Log warning removal to the warning log channel"""
    try:
        warning_log_channel_id = int(os.getenv('WARNING_LOG_CHANNEL_ID', '0'))
        if warning_log_channel_id == 0:
            return
            
        warning_log_channel = interaction.guild.get_channel(warning_log_channel_id)
        if not warning_log_channel:
            return
        
        embed = discord.Embed(
            title="Warning Removal Log",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="User", value=f"{user.display_name} ({user.id})", inline=True)
        embed.add_field(name="Removed by", value=f"{interaction.user.mention} ({interaction.user})", inline=True)
        embed.add_field(name="Warning(s)", value=warning_info, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        
        # Add warning info to footer if it's a specific warning ID
        if " (" not in warning_info and len(warning_info) < 50:  # Likely a single warning ID
            embed.set_footer(text=f"Warning ID: {warning_info}")
        
        await warning_log_channel.send(embed=embed)
    except Exception as e:
        print(f"Error logging warning removal: {e}")

@bot.tree.command(name="lookup", description="Look up warning details by ID")
@app_commands.describe(warning_id="The warning ID to look up")
async def lookup_command(interaction: discord.Interaction, warning_id: str):
    db = DatabaseManager()
    data = await db.load_data()
    
    if warning_id not in data["warnings"]:
        embed = discord.Embed(
            title="Warning Not Found",
            description=f"Warning ID `{warning_id}` not found.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    warning = data["warnings"][warning_id]
    user = interaction.guild.get_member(warning["user_id"])
    moderator = bot.get_user(warning["moderator_id"])
    
    embed = discord.Embed(
        title="Warning Details",
        color=discord.Color.blue() if not warning.get("removed", False) else discord.Color.gray(),
        timestamp=discord.utils.parse_time(warning["timestamp"])
    )
    
    embed.add_field(name="Warning ID", value=warning_id, inline=True)
    embed.add_field(name="User", value=user.mention if user else f"<@{warning['user_id']}>", inline=True)
    embed.add_field(name="Violation", value=warning["violation_type"], inline=True)
    embed.add_field(name="Points", value=str(warning["points"]), inline=True)
    embed.add_field(name="Moderator", value=moderator.mention if moderator else f"<@{warning['moderator_id']}>", inline=True)
    
    status = "Removed" if warning.get("removed", False) else "Active"
    embed.add_field(name="Status", value=status, inline=True)
    
    if warning.get("removed", False):
        removed_by = bot.get_user(warning.get("removed_by"))
        embed.add_field(name="Removed by", value=removed_by.mention if removed_by else f"<@{warning.get('removed_by')}>", inline=True)
        embed.add_field(name="Removal Reason", value=warning.get("removal_reason", "No reason"), inline=True)
    
    embed.add_field(name="Reason", value=warning["reason"], inline=False)
    
    if warning["clips"]:
        clips_text = format_clip_text(warning["clips"], use_newlines=True)
        if len(clips_text) > 1024:
            clips_text = clips_text[:1000] + "... (truncated)"
        embed.add_field(name="Evidence", value=clips_text, inline=False)
    
    if user:
        embed.set_thumbnail(url=user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="license", description="Manage user licenses")
@app_commands.describe(
    action="Action to perform (add, remove, check)",
    user="The user to manage license for",
    license_key="The license key (required for add action)",
    note="Additional note for the license (optional)"
)
async def license_command(
    interaction: discord.Interaction,
    action: str,
    user: discord.User,
    license_key: Optional[str] = None,
    note: Optional[str] = ""
):
    # Check if user has permission
    moderator_roles = [int(role_id) for role_id in os.getenv('MODERATOR_ROLES', '').split(',') if role_id]
    user_role_ids = [role.id for role in interaction.user.roles]
    
    if not any(role_id in user_role_ids for role_id in moderator_roles):
        await interaction.response.send_message("You don't have permission to manage licenses.", ephemeral=True)
        return
    
    action = action.lower()
    if action not in ["add", "remove", "check"]:
        embed = discord.Embed(
            title="Invalid Action",
            description="Valid actions are: `add`, `remove`, `check`",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    target_user = user
    
    license_manager = LicenseManager()
    
    if action == "add":
        if not license_key:
            embed = discord.Embed(
                title="License Key Required",
                description="You must provide a license key when adding a license.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Validate license key format (basic validation)
        if len(license_key) != 40 or not all(c in '0123456789abcdef' for c in license_key.lower()):
            embed = discord.Embed(
                title="Invalid License Format",
                description="License key should be 40 characters long and contain only hexadecimal characters.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        success = await license_manager.add_license(target_user.id, license_key.lower(), interaction.user.id, note)
        
        if success:
            embed = discord.Embed(
                title="License Added",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="User", value=f"{target_user.display_name} ({target_user.id})", inline=True)
            embed.add_field(name="License", value=f"`{license_key.lower()}`", inline=True)
            embed.add_field(name="Added by", value=interaction.user.mention, inline=True)
            if note:
                embed.add_field(name="Note", value=note, inline=False)
            
            # Log to warning log channel
            await log_license_action(interaction, target_user, "add", license_key.lower(), note)
        else:
            # Check if license exists
            existing_user_info = await license_manager.get_license_user(license_key.lower())
            if existing_user_info:
                existing_user_id = existing_user_info["user_id"]
                embed = discord.Embed(
                    title="License Already Assigned",
                    description=f"License `{license_key.lower()}` is already assigned to <@{existing_user_id}>",
                    color=discord.Color.red()
                )
            else:
                embed = discord.Embed(
                    title="Error Adding License",
                    description="An error occurred while adding the license.",
                    color=discord.Color.red()
                )
        
    elif action == "remove":
        success = await license_manager.remove_license(target_user.id, interaction.user.id, note or "Manual removal")
        
        if success:
            embed = discord.Embed(
                title="License Removed",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="User", value=f"{target_user.display_name} ({target_user.id})", inline=True)
            embed.add_field(name="Removed by", value=interaction.user.mention, inline=True)
            if note:
                embed.add_field(name="Reason", value=note, inline=False)
            
            # Log to warning log channel
            await log_license_action(interaction, target_user, "remove", None, note or "Manual removal")
        else:
            embed = discord.Embed(
                title="No License Found",
                description=f"No license found for {target_user.display_name}",
                color=discord.Color.red()
            )
    
    elif action == "check":
        license_info = await license_manager.get_user_license(target_user.id)
        
        embed = discord.Embed(
            title=f"License Info for {target_user.display_name}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        if license_info:
            embed.add_field(name="License", value=f"`{license_info['license']}`", inline=True)
            added_by = bot.get_user(license_info['added_by'])
            embed.add_field(name="Added by", value=added_by.mention if added_by else f"<@{license_info['added_by']}>", inline=True)
            embed.add_field(name="Added", value=f"<t:{int(discord.utils.parse_time(license_info['added_at']).timestamp())}:R>", inline=True)
            if license_info.get('note'):
                embed.add_field(name="Note", value=license_info['note'], inline=False)
        else:
            embed.add_field(name="Status", value="No license assigned", inline=False)
        
        embed.set_thumbnail(url=target_user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="licenselookup", description="Look up a license or search for licenses")
@app_commands.describe(
    query="License key to look up or partial search term"
)
async def license_lookup_command(interaction: discord.Interaction, query: str):
    license_manager = LicenseManager()
    
    # First try exact license lookup
    if len(query) == 40 and all(c in '0123456789abcdef' for c in query.lower()):
        user_info = await license_manager.get_license_user(query.lower())
        
        if user_info:
            user_id = user_info["user_id"]
            user = bot.get_user(user_id)
            added_by = bot.get_user(user_info['added_by'])
            
            embed = discord.Embed(
                title="License Details",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="License", value=f"`{query.lower()}`", inline=False)
            embed.add_field(name="User", value=user.mention if user else f"<@{user_id}>", inline=True)
            embed.add_field(name="Added by", value=added_by.mention if added_by else f"<@{user_info['added_by']}>", inline=True)
            embed.add_field(name="Added", value=f"<t:{int(discord.utils.parse_time(user_info['added_at']).timestamp())}:R>", inline=True)
            if user_info.get('note'):
                embed.add_field(name="Note", value=user_info['note'], inline=False)
            
            if user:
                embed.set_thumbnail(url=user.display_avatar.url)
        else:
            embed = discord.Embed(
                title="License Not Found",
                description=f"No user found with license: `{query.lower()}`",
                color=discord.Color.red()
            )
    else:
        # Search for partial matches
        results = await license_manager.search_licenses(query)
        
        if results:
            embed = discord.Embed(
                title=f"License Search Results for '{query}'",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            for i, result in enumerate(results[:10]):  # Limit to 10 results
                user = bot.get_user(result["user_id"])
                user_name = user.display_name if user else f"Unknown User ({result['user_id']})"
                
                embed.add_field(
                    name=f"{i+1}. {result['license'][:8]}...{result['license'][-8:]}",
                    value=f"User: {user_name}\nAdded: <t:{int(discord.utils.parse_time(result['added_at']).timestamp())}:R>",
                    inline=True
                )
            
            if len(results) > 10:
                embed.set_footer(text=f"Showing 10 of {len(results)} results")
        else:
            embed = discord.Embed(
                title="No Results",
                description=f"No licenses found matching: `{query}`",
                color=discord.Color.red()
            )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

async def log_license_action(interaction: discord.Interaction, user: discord.User, action: str, license_key: str = None, note: str = ""):
    """Log license actions to the warning log channel"""
    try:
        warning_log_channel_id = int(os.getenv('WARNING_LOG_CHANNEL_ID', '0'))
        if warning_log_channel_id == 0:
            return
            
        warning_log_channel = interaction.guild.get_channel(warning_log_channel_id)
        if not warning_log_channel:
            return
        
        embed = discord.Embed(
            title=f"License {action.title()} Log",
            color=discord.Color.purple(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="User", value=f"{user.display_name} ({user.id})", inline=True)
        embed.add_field(name="Action", value=action.title(), inline=True)
        embed.add_field(name="Moderator", value=f"{interaction.user.mention} ({interaction.user})", inline=True)
        
        if license_key:
            embed.add_field(name="License", value=f"`{license_key}`", inline=False)
        
        if note:
            embed.add_field(name="Note/Reason", value=note, inline=False)
        
        embed.set_thumbnail(url=user.display_avatar.url)
        
        await warning_log_channel.send(embed=embed)
    except Exception as e:
        print(f"Error logging license action: {e}")

@bot.tree.command(name="sync", description="Manually sync bot commands (Owner only)")
async def sync_command(interaction: discord.Interaction):
    """Manual command sync for debugging purposes"""
    # Check if user is bot owner
    app_info = await bot.application_info()
    if interaction.user.id != app_info.owner.id:
        await interaction.response.send_message("Only the bot owner can use this command.", ephemeral=True)
        return
    
    try:
        # Clear global commands to avoid conflicts
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()  # Clear global
        
        # Sync only to Seasons guild
        guild_id = 1365988649665036288  # Seasons RP
        guild = discord.Object(id=guild_id)
        synced = await bot.tree.sync(guild=guild)
        
        embed = discord.Embed(
            title="Command Sync Complete",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Method", value="Guild-only sync (instant)", inline=True)
        embed.add_field(name="Commands Synced", value=f"{len(synced)} commands", inline=True)
        embed.add_field(name="Guild ID", value=str(guild_id), inline=True)
        embed.add_field(name="Note", value="Commands should appear immediately in this guild.", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        await interaction.response.send_message(f"Sync failed: {e}", ephemeral=True)

def main():
    """Main function to ensure all commands are loaded before running bot"""
    # Ensure all commands are loaded by checking the command tree
    import time
    time.sleep(0.1)  # Small delay to ensure all decorators are processed
    
    command_count = len(bot.tree.get_commands())
    if command_count == 0:
        print("ERROR: No commands registered! Bot will not work properly.")
        return
    
    token = os.getenv('DISCORD_TOKEN') or os.getenv('BOT_TOKEN')
    if not token:
        print("Error: DISCORD_TOKEN or BOT_TOKEN not found in environment variables")
        exit(1)
    
    bot.run(token)

if __name__ == "__main__":
    main()