"""
Credit utility functions for managing user credits and credit-based actions.
Uses the existing database functions for credit checking and deduction.
"""

import logging
from typing import Dict, Any, Optional, Tuple
from app.utils.supabase_utils import supabase_manager
from app.logging_config import get_logger

logger = get_logger(__name__)


class CreditManager:
    """Manages user credits and credit-based actions."""
    
    def __init__(self):
        """Initialize the credit manager."""
        self.supabase = supabase_manager
    
    def check_user_credits(self, user_id: str) -> Dict[str, Any]:
        """
        Check user's current credit status.
        
        Args:
            user_id: The user's UUID
            
        Returns:
            Dict containing credit information
        """
        try:
            if not self.supabase.is_connected():
                logger.error("Supabase not connected")
                return {"error": "Database connection failed"}
            
            # Call the get_user_credits function
            result = self.supabase.client.rpc(
                'get_user_credits',
                {'user_uuid': user_id}
            ).execute()
            
            if result.data:
                credit_info = result.data[0]
                logger.info(f"Retrieved credit info for user {user_id}: {credit_info}")
                return credit_info
            else:
                logger.warning(f"No credit info found for user {user_id}")
                return {
                    "total_credits": 0,
                    "used_credits": 0,
                    "available_credits": 0,
                    "subscription_status": "no_subscription",
                    "plan_name": "no_plan",
                    "plan_display_name": "No Plan"
                }
                
        except Exception as e:
            logger.error(f"Error checking credits for user {user_id}: {e}")
            return {"error": f"Failed to check credits: {str(e)}"}
    
    def can_perform_action(self, user_id: str, action_name: str) -> Dict[str, Any]:
        """
        Check if user can perform a specific action based on credits and limits.
        
        Args:
            user_id: The user's UUID
            action_name: The action to check (e.g., 'scraping', 'generate_scenario')
            
        Returns:
            Dict containing whether action can be performed and reason
        """
        try:
            if not self.supabase.is_connected():
                logger.error("Supabase not connected")
                return {"error": "Database connection failed"}
            
            # Call the can_perform_action function
            result = self.supabase.client.rpc(
                'can_perform_action',
                {
                    'user_uuid': user_id,
                    'action_name': action_name
                }
            ).execute()
            
            if result.data:
                action_info = result.data[0]
                logger.info(f"Action check for user {user_id}, action {action_name}: {action_info}")
                return action_info
            else:
                logger.warning(f"No action info found for user {user_id}, action {action_name}")
                return {"error": "Action check failed"}
                
        except Exception as e:
            logger.error(f"Error checking action for user {user_id}, action {action_name}: {e}")
            return {"error": f"Failed to check action: {str(e)}"}
    
    def deduct_credits(self, user_id: str, action_name: str, reference_id: Optional[str] = None, 
                       reference_type: Optional[str] = None, description: Optional[str] = None) -> bool:
        """
        Deduct credits from user for performing an action.
        
        Args:
            user_id: The user's UUID
            action_name: The action being performed (e.g., 'scraping')
            reference_id: Optional reference ID for the action
            reference_type: Optional reference type
            description: Optional description of the action
            
        Returns:
            True if credits were deducted successfully, False otherwise
        """
        try:
            if not self.supabase.is_connected():
                logger.error("Supabase not connected")
                return False
            
            # Call the deduct_user_credits function
            result = self.supabase.client.rpc(
                'deduct_user_credits',
                {
                    'user_uuid': user_id,
                    'action_name': action_name,
                    'reference_id': reference_id,
                    'reference_type': reference_type,
                    'description': description
                }
            ).execute()
            
            # Handle different return types from Supabase RPC
            success = False
            if isinstance(result.data, bool):
                success = result.data
            elif isinstance(result.data, list) and result.data:
                success = bool(result.data[0])
            else:
                success = bool(result.data)  # Fallback for other unexpected formats
            
            if success:
                logger.info(f"Successfully deducted credits for user {user_id}, action {action_name}")
                return True
            else:
                logger.warning(f"Failed to deduct credits for user {user_id}, action {action_name} - result.data: {result.data}")
                return False
                
        except Exception as e:
            logger.error(f"Error deducting credits for user {user_id}, action {action_name}: {e}")
            return False
    
    def add_credits(self, user_id: str, action_name: str, credits_amount: int, 
                    reference_id: Optional[str] = None, reference_type: Optional[str] = None, 
                    description: Optional[str] = None) -> bool:
        """
        Add credits to user account.
        
        Args:
            user_id: The user's UUID
            action_name: The action type (e.g., 'purchase', 'refund')
            credits_amount: Number of credits to add
            reference_id: Optional reference ID
            reference_type: Optional reference type
            description: Optional description
            
        Returns:
            True if credits were added successfully, False otherwise
        """
        try:
            if not self.supabase.is_connected():
                logger.error("Supabase not connected")
                return False
            
            # Call the add_user_credits function
            result = self.supabase.client.rpc(
                'add_user_credits',
                {
                    'user_uuid': user_id,
                    'action_name': action_name,
                    'credits_amount': credits_amount,
                    'reference_id': reference_id,
                    'reference_type': reference_type,
                    'description': description
                }
            ).execute()
            
            # Handle different return types from Supabase RPC
            success = False
            if isinstance(result.data, bool):
                success = result.data
            elif isinstance(result.data, list) and result.data:
                success = bool(result.data[0])
            else:
                success = bool(result.data)  # Fallback for other unexpected formats
            
            if success:
                logger.info(f"Successfully added {credits_amount} credits for user {user_id}")
                return True
            else:
                logger.warning(f"Failed to add credits for user {user_id} - result.data: {result.data}")
                return False
                
        except Exception as e:
            logger.error(f"Error adding credits for user {user_id}: {e}")
            return False
    
    def get_credit_cost(self, action_name: str) -> Optional[int]:
        """
        Get the credit cost for a specific action.
        
        Args:
            action_name: The action name
            
        Returns:
            Credit cost or None if not found
        """
        try:
            if not self.supabase.is_connected():
                logger.error("Supabase not connected")
                return None
            
            # Query the credit_actions table
            result = self.supabase.client.table('credit_actions').select('base_credit_cost').eq('action_name', action_name).execute()
            
            if result.data:
                cost = result.data[0]['base_credit_cost']
                logger.info(f"Credit cost for action {action_name}: {cost}")
                return cost
            else:
                logger.warning(f"No credit cost found for action {action_name}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting credit cost for action {action_name}: {e}")
            return None


# Global credit manager instance
credit_manager = CreditManager()


def check_user_credits(user_id: str) -> Dict[str, Any]:
    """Convenience function to check user credits."""
    return credit_manager.check_user_credits(user_id)


def can_perform_action(user_id: str, action_name: str) -> Dict[str, Any]:
    """Convenience function to check if user can perform an action."""
    return credit_manager.can_perform_action(user_id, action_name)


def deduct_credits(user_id: str, action_name: str, reference_id: Optional[str] = None, 
                   reference_type: Optional[str] = None, description: Optional[str] = None) -> bool:
    """Convenience function to deduct credits."""
    return credit_manager.deduct_credits(user_id, action_name, reference_id, reference_type, description)


def add_credits(user_id: str, action_name: str, credits_amount: int, 
                reference_id: Optional[str] = None, reference_type: Optional[str] = None, 
                description: Optional[str] = None) -> bool:
    """Convenience function to add credits."""
    return credit_manager.add_credits(user_id, action_name, credits_amount, reference_id, reference_type, description)


def get_credit_cost(action_name: str) -> Optional[int]:
    """Convenience function to get credit cost for an action."""
    return credit_manager.get_credit_cost(action_name)
