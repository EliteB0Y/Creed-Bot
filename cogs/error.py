import discord
from discord.ext import commands

class CommandErrorHandler(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if hasattr(ctx.command, 'on_error'):
            return

        cog = ctx.cog
        if cog:
            if cog._get_overridden_method(cog.cog_command_error) is not None:
                return

        ignored = (commands.CommandNotFound, commands.errors.CommandNotFound)
        error = getattr(error, 'original', error)

        e = discord.Embed(color=discord.Color.red())

        if isinstance(error, ignored):
            return
        
        elif isinstance(error, commands.BotMissingPermissions) or isinstance(error, commands.MissingPermissions):
            e.description = f"Hi {ctx.author.name}, I do not have the following permissions to execute this command: {error.missing_perms}`"
            await ctx.send(embed = e)

        elif isinstance(error, commands.DisabledCommand):
            e.description = f"> {self.client.emotes.get('redtick', '')} **{ctx.command} command is disabled by the owner.**"
            await ctx.send(embed=e)

        elif isinstance(error, commands.NoPrivateMessage):
            try:
                e.description = f"> {self.client.emotes.get('redtick', '')} **{ctx.command} command can not be used in Private Messages.**"
                await ctx.send(embed=e)
            except discord.HTTPException:
                pass
        
        elif isinstance(error, commands.CommandOnCooldown):
            if ctx.author.id == self.client.owner_id:
                return await ctx.reinvoke()
            else:
                e.description = f"> {self.client.emotes.get('redtick', '')} **You are on cooldown. Please retry after {round(error.retry_after)}s.**"
            await ctx.send(embed = e, delete_after=round(error.retry_after))
        
        elif isinstance(error, commands.CheckFailure):
            if ctx.author.id == self.client.owner_id:
                return await ctx.reinvoke()
            else:
                e.description = f"> {self.client.emotes.get('redtick', '')} **You cannot use this command as: {str(error)}**"
                await ctx.send(embed=e)

        elif isinstance(error, commands.BadArgument):
            e.description = f"> {self.client.emotes.get('redtick', '')} **{str(error)}**"
            await ctx.send(embed=e)

        else:
            print(f"Ignoring exception in command {ctx.command}: {str(error)}")

async def setup(bot):
    await bot.add_cog(CommandErrorHandler(bot))